#!/usr/bin/env python3
"""Fail-closed ingestion of future Zhihu answers and articles.

The article body is data. This program does not follow instructions inside a
manifest, does not anonymize text, and does not fetch Zhihu. A row from the
collector CSV cannot become a page: that file has no body and no exact time.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 1
BASELINE_ID = "zhihu-site-baseline-2026-11-21"
SHANGHAI = timezone(timedelta(hours=8))
MAX_BODY_CHARS = 400_000
MAX_DECK_CHARS = 180
MAX_TITLE_CHARS = 500
EXIT_OK = 0
EXIT_HOLD = 10
EXIT_REJECT = 11
EXIT_ERROR = 1

PRIVACY_ATTESTATION = (
    "Reviewed separately from ingestion. "
    "No named third parties, identifiable private experiences, "
    "or institution-plus-number combinations remain. "
    "No searchable direct quote that identifies a person remains. "
    "Ambiguous passages were held rather than rewritten. "
    "Names were not replaced with placeholders. "
    "The argument was not changed. "
    "This clearance is not a regex or automatic anonymizer."
)

ALLOWED_TOP_LEVEL = {
    "schema_version",
    "item",
    "provenance",
    "baseline",
    "privacy_clearance",
    "publish_approval",
    "hold_release",
}
ALLOWED_ITEM = {
    "kind",
    "id",
    "question_id",
    "canonical_url",
    "state",
    "title",
    "body_markdown",
    "body_sha256",
    "deck",
    "deck_provenance",
}
ALLOWED_PROVENANCE = {
    "producer",
    "collected_at",
    "published_at",
    "modified_at",
    "time_source",
    "published_at_precision",
    "modified_at_precision",
    "collected_at_precision",
}
ALLOWED_BASELINE = {"baseline_id", "relation"}
ALLOWED_PRIVACY = {
    "status",
    "method",
    "cleared_by",
    "cleared_at",
    "attestation",
    "hold_reasons",
    "argument_unchanged",
    "name_substitution_used",
    "regex_anonymizer_used",
}
ALLOWED_APPROVAL = {"decision", "approval_id", "approved_by", "approved_at"}
ALLOWED_RELEASE = {"hold_id", "confirm_token"}
PATH_KEYS = {"body_path", "raw_path", "file_path", "local_path", "source_path"}
SECRET_KEYS = {
    "access_token",
    "cookie",
    "authorization",
    "password",
    "secret",
    "refresh_token",
    "zhihu_access_secret",
}
CSV_COLUMNS = ("title", "type", "date", "upvotes", "comments", "favorites", "url")
ANSWER_URL = re.compile(
    r"^https://www\.zhihu\.com/question/(?P<qid>[0-9]{1,24})/answer/(?P<aid>[0-9]{1,24})$"
)
ARTICLE_URL = re.compile(r"^https://zhuanlan\.zhihu\.com/p/(?P<pid>[0-9]{1,24})$")
ID_TEXT = re.compile(r"^[0-9]{1,24}$")
DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
INSTANT_TEXT = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$"
)
APPROVAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{8,200}$")
PRODUCER_TEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
CONFIRM_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,200}$")
SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SLUG_TEXT = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KIND_FROM_CSV = {
    "回答": "answer",
    "answer": "answer",
    "文章": "article",
    "article": "article",
    "专栏": "article",
}
OUT_OF_SCOPE_CSV = {
    "评论": "comment",
    "comment": "comment",
    "草稿": "draft",
    "draft": "draft",
}


class ZhihuIngestError(RuntimeError):
    """Raised when the tool itself cannot safely continue."""


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def sync_dir(root: Path) -> Path:
    return root / "scripts" / "zhihu-sync"


def baseline_path(root: Path) -> Path:
    return sync_dir(root) / "baseline.json"


def ledger_path(root: Path) -> Path:
    return sync_dir(root) / "ledger.json"


def catalog_path(root: Path) -> Path:
    return root / "content" / "article-catalog.json"


def forbidden_needles() -> tuple[str, ...]:
    # Kept as code points so the public source does not spell the private name.
    private_name = chr(0x9EC4) + chr(0x5357) + chr(0x6A35)
    return (
        private_name,
        "C:\\Users\\",
        "AppData",
        "ZHIHU_ACCESS_SECRET",
        "Access Secret",
        "chatgpt.com/g/",
        "ChatGPT Exporter",
        "PSPath",
        "PSParentPath",
    )


def normalize_body(value: str) -> str:
    if value.startswith("\ufeff"):
        value = value[1:]
    return value.replace("\r\n", "\n").replace("\r", "\n")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def parse_instant(value: Any) -> datetime | None:
    if not isinstance(value, str) or not INSTANT_TEXT.fullmatch(value):
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return None
    return parsed


def json_ready(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, value: Any) -> None:
    atomic_write(path, json_ready(value))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


@contextmanager
def project_lock(root: Path) -> Iterator[None]:
    lock_path = sync_dir(root) / ".ingest.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 5
    descriptor: int | None = None
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ZhihuIngestError("Zhihu ingest lock is still held")
            time.sleep(0.05)
    try:
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        lock_path.unlink(missing_ok=True)


def add_code(items: list[str], code: str) -> None:
    if code not in items:
        items.append(code)


def walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def contains_secret_text(value: Any) -> bool:
    needles = ("ZHIHU_ACCESS_SECRET", "Access Secret")
    if isinstance(value, str):
        return any(needle in value for needle in needles)
    if isinstance(value, dict):
        return any(contains_secret_text(child) for child in value.values())
    if isinstance(value, list):
        return any(contains_secret_text(child) for child in value)
    return False


def blank_result() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "decision": "reject",
        "reasons": [],
        "unknown_fields": [],
        "identity": {"kind": None, "id": None, "canonical_url": None},
        "wrote": False,
        "slug": None,
    }


def parse_canonical_url(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, str) or not value.startswith("https://"):
        return None
    if "?" in value or "#" in value or value.endswith("/"):
        return None
    answer = ANSWER_URL.fullmatch(value)
    if answer:
        return {
            "kind": "answer",
            "id": answer.group("aid"),
            "question_id": answer.group("qid"),
            "canonical_url": value,
        }
    article = ARTICLE_URL.fullmatch(value)
    if article:
        return {
            "kind": "article",
            "id": article.group("pid"),
            "question_id": None,
            "canonical_url": value,
        }
    return None


def normalize_title(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def file_body_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    return sha256_text(normalize_body(path.read_text(encoding="utf-8")))


def catalog_by_source(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for article in catalog.get("articles", []):
        source = article.get("source")
        if isinstance(source, dict) and isinstance(source.get("url"), str):
            found[source["url"]] = article
    return found


def ledger_matches(items: list[dict[str, Any]], kind: str | None, item_id: str | None, url: str | None) -> dict[str, Any] | None:
    for entry in items:
        same_id = kind is not None and item_id is not None and entry.get("kind") == kind and entry.get("id") == item_id
        same_url = url is not None and entry.get("canonical_url") == url
        if same_id or same_url:
            return entry
    return None


def hold_matches(hold: dict[str, Any], kind: str | None, item_id: str | None, url: str | None, title: str | None) -> bool:
    if hold.get("id") and item_id and hold.get("kind") == kind and hold.get("id") == item_id:
        return True
    if hold.get("canonical_url") and url and hold.get("canonical_url") == url:
        return True
    if hold.get("id") or hold.get("canonical_url"):
        return False
    hold_title = hold.get("title")
    if isinstance(title, str) and isinstance(hold_title, str) and title.strip() and hold_title.strip():
        return normalize_title(title) == normalize_title(hold_title)
    return False


def next_buzz_order(catalog: dict[str, Any]) -> int:
    orders = [
        article.get("order")
        for article in catalog.get("articles", [])
        if article.get("section") == "buzz" and isinstance(article.get("order"), int) and not isinstance(article.get("order"), bool)
    ]
    candidate = (min(orders) - 10) if orders else 0
    used = {
        article.get("order")
        for article in catalog.get("articles", [])
        if article.get("section") == "buzz"
    }
    while candidate in used:
        candidate -= 10
    return candidate


def shanghai_day(instant: datetime) -> str:
    return instant.astimezone(SHANGHAI).date().isoformat()


def check_object_keys(value: Any, allowed: set[str], label: str, reject: list[str]) -> None:
    if not isinstance(value, dict):
        return
    for key in value:
        if key not in allowed:
            add_code(reject, "unknown_manifest_field")
            if key in PATH_KEYS:
                add_code(reject, "body_path_not_accepted")


def read_time_field(
    payload: dict[str, Any],
    name: str,
    precision_name: str,
    unknown_fields: list[str],
    reject: list[str],
    hold: list[str],
) -> datetime | None:
    if precision_name not in payload or payload.get(precision_name) is None:
        add_code(unknown_fields, f"provenance.{precision_name}")
        add_code(hold, "time_precision_unknown")
        return None
    precision = payload.get(precision_name)
    if precision not in {"instant", "day", "unknown"}:
        add_code(reject, "time_precision_invalid")
        return None
    if precision != "instant":
        # A day or an unknown precision is not an exact instant. Keep it unknown.
        add_code(hold, "time_source_not_exact")
        add_code(unknown_fields, f"provenance.{name}")
        return None
    if name not in payload or payload.get(name) is None:
        add_code(unknown_fields, f"provenance.{name}")
        add_code(hold, f"{name}_unknown")
        return None
    parsed = parse_instant(payload.get(name))
    if parsed is None:
        if isinstance(payload.get(name), str) and DATE_ONLY.fullmatch(payload[name]):
            add_code(reject, "precision_contradiction")
        else:
            add_code(reject, "timestamp_invalid")
        return None
    return parsed


def privacy_gate(raw: dict[str, Any], unknown_fields: list[str], reject: list[str], hold: list[str]) -> None:
    if "privacy_clearance" not in raw or raw.get("privacy_clearance") is None:
        add_code(unknown_fields, "privacy_clearance")
        add_code(hold, "privacy_unreviewed")
        return
    privacy = raw.get("privacy_clearance")
    if not isinstance(privacy, dict):
        add_code(reject, "privacy_clearance_invalid")
        return
    check_object_keys(privacy, ALLOWED_PRIVACY, "privacy_clearance", reject)
    status = privacy.get("status")
    if status is None:
        add_code(unknown_fields, "privacy_clearance.status")
        add_code(hold, "privacy_unreviewed")
        return
    if status == "unreviewed":
        add_code(hold, "privacy_unreviewed")
        return
    if status == "held":
        reasons = privacy.get("hold_reasons")
        if not isinstance(reasons, list) or not reasons or not all(isinstance(item, str) and item.strip() for item in reasons):
            add_code(hold, "privacy_clearance_rejected")
        add_code(hold, "privacy_held")
        return
    if status != "cleared":
        add_code(reject, "privacy_clearance_invalid")
        return
    method = privacy.get("method")
    if method != "separate_review":
        add_code(hold, "privacy_clearance_rejected")
    if privacy.get("name_substitution_used") is not False or privacy.get("regex_anonymizer_used") is not False:
        add_code(hold, "privacy_clearance_rejected")
    if privacy.get("argument_unchanged") is not True:
        add_code(hold, "privacy_clearance_rejected")
    if privacy.get("hold_reasons") != []:
        add_code(hold, "privacy_clearance_rejected")
    if privacy.get("attestation") != PRIVACY_ATTESTATION:
        add_code(hold, "privacy_clearance_rejected")
    cleared_by = privacy.get("cleared_by")
    if not isinstance(cleared_by, str) or not PRODUCER_TEXT.fullmatch(cleared_by):
        add_code(hold, "privacy_clearance_rejected")
    if parse_instant(privacy.get("cleared_at")) is None:
        add_code(hold, "privacy_clearance_rejected")


def approval_block(raw: dict[str, Any], reject: list[str], hold: list[str]) -> str | None:
    if "publish_approval" not in raw or raw.get("publish_approval") is None:
        add_code(hold, "approval_required")
        return None
    approval = raw.get("publish_approval")
    if not isinstance(approval, dict):
        add_code(reject, "approval_malformed")
        return None
    check_object_keys(approval, ALLOWED_APPROVAL, "publish_approval", reject)
    if approval.get("decision") != "approve":
        add_code(hold, "approval_required")
        return None
    approval_id = approval.get("approval_id")
    approved_by = approval.get("approved_by")
    if not isinstance(approval_id, str) or not APPROVAL_ID.fullmatch(approval_id):
        add_code(reject, "approval_malformed")
        return None
    if not isinstance(approved_by, str) or not PRODUCER_TEXT.fullmatch(approved_by):
        add_code(reject, "approval_malformed")
        return None
    if parse_instant(approval.get("approved_at")) is None:
        add_code(reject, "approval_malformed")
        return None
    return approval_id


def site_boundary(texts: list[str], hold: list[str]) -> None:
    needles = forbidden_needles()
    for text in texts:
        if any(needle in text for needle in needles):
            add_code(hold, "site_privacy_boundary")
            return


def load_state(root: Path) -> dict[str, Any]:
    baseline_file = baseline_path(root)
    ledger_file = ledger_path(root)
    catalog_file = catalog_path(root)
    missing = [
        name
        for name, path in (
            ("baseline_missing", baseline_file),
            ("ledger_missing", ledger_file),
            ("catalog_missing", catalog_file),
        )
        if not path.is_file()
    ]
    if missing:
        result = blank_result()
        result["reasons"] = missing
        return {"error": result}
    baseline = read_json(baseline_file)
    ledger = read_json(ledger_file)
    catalog = read_json(catalog_file)
    if not isinstance(baseline, dict) or not isinstance(ledger, dict) or not isinstance(catalog, dict):
        result = blank_result()
        result["reasons"] = ["state_invalid"]
        return {"error": result}
    if baseline.get("baseline_id") != BASELINE_ID or not parse_instant(baseline.get("sealed_at")):
        result = blank_result()
        result["reasons"] = ["baseline_invalid"]
        return {"error": result}
    if not isinstance(baseline.get("known"), list) or not isinstance(baseline.get("holds"), list):
        result = blank_result()
        result["reasons"] = ["baseline_invalid"]
        return {"error": result}
    if not isinstance(ledger.get("items"), list) or not isinstance(catalog.get("articles"), list):
        result = blank_result()
        result["reasons"] = ["state_invalid"]
        return {"error": result}
    return {"baseline": baseline, "ledger": ledger, "catalog": catalog}


def existing_publication(
    state: dict[str, Any],
    kind: str | None,
    item_id: str | None,
    url: str | None,
) -> dict[str, Any] | None:
    ledger_entry = ledger_matches(state["ledger"]["items"], kind, item_id, url)
    catalog_entry = catalog_by_source(state["catalog"]).get(url) if url else None
    known = None
    for entry in state["baseline"]["known"]:
        if not isinstance(entry, dict):
            continue
        same_id = kind and item_id and entry.get("kind") == kind and entry.get("id") == item_id
        same_url = url and entry.get("canonical_url") == url
        if same_id or same_url:
            known = entry
            break
    if ledger_entry is None and catalog_entry is None and known is None:
        return None
    return {"ledger": ledger_entry, "catalog": catalog_entry, "known": known}


def content_hash_for_existing(root: Path, existing: dict[str, Any]) -> str | None:
    catalog_entry = existing.get("catalog")
    if isinstance(catalog_entry, dict) and isinstance(catalog_entry.get("content"), str):
        relative = catalog_entry["content"]
        path = (root / relative).resolve()
        content_root = (root / "content").resolve()
        if path == content_root or content_root in path.parents:
            return file_body_hash(path)
    ledger_entry = existing.get("ledger")
    if isinstance(ledger_entry, dict):
        return ledger_entry.get("body_sha256")
    return None


def plan_manifest(
    manifest: Any,
    state: dict[str, Any],
    root: Path,
    mode: str,
    cli_approval: str | None,
) -> dict[str, Any]:
    result = blank_result()
    reject = result["reasons"]
    hold: list[str] = []
    unknown_fields: list[str] = result["unknown_fields"]
    if not isinstance(manifest, dict):
        add_code(reject, "expected_object")
        return result
    if any(key in PATH_KEYS for key in walk_keys(manifest)):
        add_code(reject, "body_path_not_accepted")
    if any(str(key).lower() in SECRET_KEYS for key in walk_keys(manifest)) or contains_secret_text(manifest):
        add_code(reject, "secret_material")
        return result
    for key in manifest:
        if key not in ALLOWED_TOP_LEVEL:
            add_code(reject, "unknown_manifest_field")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        add_code(reject, "schema_version")
    item = manifest.get("item")
    if not isinstance(item, dict):
        add_code(reject, "item_invalid")
        finish(result, reject, hold)
        return result
    check_object_keys(item, ALLOWED_ITEM, "item", reject)
    kind = item.get("kind") if "kind" in item else None
    if kind is None:
        add_code(unknown_fields, "item.kind")
        add_code(hold, "identity_incomplete")
    elif kind in {"comment", "draft"}:
        add_code(reject, "kind_out_of_scope")
    elif kind not in {"answer", "article"}:
        add_code(reject, "kind_invalid")
    state_value = item.get("state") if "state" in item else None
    if state_value is None:
        add_code(unknown_fields, "item.state")
        add_code(hold, "state_unknown")
    elif state_value in {"draft", "comment", "unpublished"}:
        add_code(reject, "state_out_of_scope")
    elif state_value != "published":
        add_code(reject, "state_invalid")
    item_id = item.get("id") if "id" in item else None
    if item_id is None:
        add_code(unknown_fields, "item.id")
        add_code(hold, "identity_incomplete")
    elif not isinstance(item_id, str) or not ID_TEXT.fullmatch(item_id):
        add_code(reject, "identity_id_must_be_string")
        item_id = None
    url_value = item.get("canonical_url") if "canonical_url" in item else None
    parsed_url = parse_canonical_url(url_value)
    if url_value is None:
        add_code(unknown_fields, "item.canonical_url")
        add_code(hold, "identity_incomplete")
    elif parsed_url is None:
        add_code(reject, "canonical_url_invalid")
    else:
        result["identity"]["canonical_url"] = parsed_url["canonical_url"]
        if kind in {"answer", "article"} and parsed_url["kind"] != kind:
            add_code(reject, "canonical_url_mismatch")
        if item_id is not None and parsed_url["id"] != item_id:
            add_code(reject, "canonical_url_mismatch")
    if isinstance(kind, str) and kind in {"answer", "article"}:
        result["identity"]["kind"] = kind
    if isinstance(item_id, str):
        result["identity"]["id"] = item_id
    if kind == "answer":
        question_id = item.get("question_id") if "question_id" in item else None
        if question_id is None:
            add_code(unknown_fields, "item.question_id")
            add_code(hold, "identity_incomplete")
        elif not isinstance(question_id, str) or not ID_TEXT.fullmatch(question_id):
            add_code(reject, "identity_id_must_be_string")
        elif parsed_url and parsed_url.get("question_id") != question_id:
            add_code(reject, "canonical_url_mismatch")
    elif kind == "article" and item.get("question_id") not in (None, "") and "question_id" in item and item.get("question_id") is not None:
        add_code(reject, "canonical_url_mismatch")

    title = item.get("title") if isinstance(item.get("title"), str) else None
    if "title" not in item or item.get("title") is None:
        add_code(unknown_fields, "item.title")
        add_code(hold, "title_unknown")
    elif not isinstance(item.get("title"), str) or not item["title"].strip() or len(item["title"]) > MAX_TITLE_CHARS:
        add_code(reject, "title_invalid")
        title = None
    body = item.get("body_markdown") if "body_markdown" in item else None
    normalized = None
    if body is None:
        add_code(unknown_fields, "item.body_markdown")
        add_code(hold, "missing_body")
    elif not isinstance(body, str):
        add_code(reject, "body_type")
    elif normalize_body(body) == "":
        add_code(reject, "empty_body")
    elif len(normalize_body(body)) > MAX_BODY_CHARS:
        add_code(reject, "body_too_large")
    else:
        normalized = normalize_body(body)
        if CONTROL_CHARS.search(normalized):
            add_code(reject, "control_character")
            normalized = None
        digest = item.get("body_sha256")
        if normalized is None:
            pass
        elif digest is None:
            add_code(unknown_fields, "item.body_sha256")
            add_code(hold, "body_sha256_unknown")
        elif not isinstance(digest, str) or not SHA256_TEXT.fullmatch(digest):
            add_code(reject, "body_sha256_mismatch")
        elif digest != sha256_text(normalized):
            add_code(reject, "body_sha256_mismatch")
    deck = item.get("deck") if isinstance(item.get("deck"), str) else None
    if item.get("deck_provenance") != "exact_excerpt":
        if item.get("deck_provenance") is None:
            add_code(unknown_fields, "item.deck_provenance")
            add_code(hold, "deck_unknown")
        else:
            add_code(reject, "deck_not_excerpt")
    if deck is None:
        if "deck" not in item or item.get("deck") is None:
            add_code(unknown_fields, "item.deck")
            add_code(hold, "deck_unknown")
        else:
            add_code(reject, "deck_not_excerpt")
    elif len(deck) > MAX_DECK_CHARS or not deck.strip():
        add_code(reject, "deck_too_long" if len(deck) > MAX_DECK_CHARS else "deck_not_excerpt")
    elif normalized is not None and deck not in normalized:
        add_code(reject, "deck_not_excerpt")

    provenance = manifest.get("provenance") if isinstance(manifest.get("provenance"), dict) else None
    if provenance is None:
        add_code(unknown_fields, "provenance")
        add_code(hold, "published_at_unknown")
        add_code(hold, "modified_at_unknown")
        add_code(hold, "collected_at_unknown")
        published_at = modified_at = collected_at = None
    else:
        check_object_keys(provenance, ALLOWED_PROVENANCE, "provenance", reject)
        producer = provenance.get("producer")
        if not isinstance(producer, str) or not PRODUCER_TEXT.fullmatch(producer):
            add_code(reject, "producer_invalid")
        time_source = provenance.get("time_source")
        if time_source is None:
            add_code(unknown_fields, "provenance.time_source")
            add_code(hold, "time_source_not_exact")
        elif time_source != "exact_source_timestamp":
            add_code(hold, "time_source_not_exact")
        published_at = read_time_field(provenance, "published_at", "published_at_precision", unknown_fields, reject, hold)
        modified_at = read_time_field(provenance, "modified_at", "modified_at_precision", unknown_fields, reject, hold)
        collected_at = read_time_field(provenance, "collected_at", "collected_at_precision", unknown_fields, reject, hold)
        if published_at and modified_at and modified_at < published_at:
            add_code(reject, "provenance_time_order")
        if modified_at and collected_at and collected_at < modified_at:
            add_code(reject, "provenance_time_order")
        if published_at and collected_at and collected_at < published_at:
            add_code(reject, "provenance_time_order")

    baseline_claim = manifest.get("baseline") if isinstance(manifest.get("baseline"), dict) else None
    if baseline_claim is None:
        add_code(unknown_fields, "baseline")
        add_code(hold, "not_proven_after_baseline")
    else:
        check_object_keys(baseline_claim, ALLOWED_BASELINE, "baseline", reject)
        if baseline_claim.get("baseline_id") is None:
            add_code(unknown_fields, "baseline.baseline_id")
            add_code(hold, "baseline_id_unknown")
        elif baseline_claim.get("baseline_id") != state["baseline"]["baseline_id"]:
            add_code(reject, "baseline_id_mismatch")
        relation = baseline_claim.get("relation")
        if relation is None:
            add_code(unknown_fields, "baseline.relation")
            add_code(hold, "not_proven_after_baseline")
        elif relation not in {"after_baseline", "historic", "in_baseline", "unknown"}:
            add_code(reject, "relation_invalid")
        elif relation != "after_baseline":
            add_code(hold, "not_proven_after_baseline")

    sealed_at = parse_instant(state["baseline"]["sealed_at"])
    after_baseline = bool(
        published_at is not None
        and sealed_at is not None
        and published_at > sealed_at
        and isinstance(baseline_claim, dict)
        and baseline_claim.get("relation") == "after_baseline"
        and baseline_claim.get("baseline_id") == state["baseline"]["baseline_id"]
    )
    if published_at is not None and sealed_at is not None and published_at <= sealed_at:
        if isinstance(baseline_claim, dict) and baseline_claim.get("relation") == "after_baseline":
            add_code(reject, "relation_contradiction")
        else:
            add_code(hold, "historic_before_baseline")

    privacy_gate(manifest, unknown_fields, reject, hold)
    approval_id = approval_block(manifest, reject, hold)
    if normalized is not None:
        site_boundary([normalized, title or "", deck or ""], hold)

    identity_url = result["identity"]["canonical_url"]
    existing = existing_publication(state, result["identity"]["kind"], result["identity"]["id"], identity_url)
    matched_hold = None
    for hold_entry in state["baseline"]["holds"]:
        if isinstance(hold_entry, dict) and hold_matches(
            hold_entry,
            result["identity"]["kind"],
            result["identity"]["id"],
            identity_url,
            title,
        ):
            matched_hold = hold_entry
            break

    if existing is not None:
        prior_hash = content_hash_for_existing(root, existing)
        if normalized is None:
            finish(result, reject, hold, decision="skip", reasons=["already_on_site"])
            return result
        current_hash = sha256_text(normalized)
        if prior_hash == current_hash:
            finish(result, reject, hold, decision="skip", reasons=["idempotent_duplicate"])
            result["slug"] = (existing.get("catalog") or existing.get("ledger") or {}).get("slug")
            return result
        add_code(hold, "possible_edit_not_applied")
        finish(result, reject, hold)
        return result

    released_hold = False
    if matched_hold is not None:
        unresolved = not matched_hold.get("id") and not matched_hold.get("canonical_url")
        if unresolved:
            add_code(hold, "matches_unresolved_hold")
        confirmation = matched_hold.get("confirmation")
        release = manifest.get("hold_release")
        token_ok = (
            isinstance(confirmation, dict)
            and isinstance(release, dict)
            and release.get("hold_id") == matched_hold.get("hold_id")
            and isinstance(release.get("confirm_token"), str)
            and release.get("confirm_token") == confirmation.get("token")
        )
        if token_ok and not unresolved:
            released_hold = True
            hold[:] = [code for code in hold if code not in {"not_proven_after_baseline", "historic_before_baseline"}]
            reject[:] = [code for code in reject if code != "relation_contradiction"]
        else:
            add_code(hold, "explicit_confirmation_required")

    if matched_hold is None and not after_baseline and "historic_before_baseline" not in hold and "relation_contradiction" not in reject:
        add_code(hold, "not_proven_after_baseline")

    if reject:
        finish(result, reject, hold)
        return result
    if hold:
        finish(result, reject, hold)
        return result

    if (
        published_at is None
        or modified_at is None
        or collected_at is None
        or normalized is None
        or title is None
        or deck is None
        or approval_id is None
        or identity_url is None
        or kind not in {"answer", "article"}
        or not isinstance(item_id, str)
    ):
        add_code(hold, "not_proven_after_baseline")
        finish(result, reject, hold)
        return result

    if mode == "evaluate":
        result["decision"] = "eligible"
        result["reasons"] = []
        return attach_slug(result, item_id, kind)
    if cli_approval is None:
        add_code(hold, "cli_approval_required")
        finish(result, reject, hold)
        return result
    if cli_approval != approval_id:
        add_code(hold, "approval_mismatch")
        finish(result, reject, hold)
        return result

    slug = f"zhihu-{kind}-{item_id}"
    if not SLUG_TEXT.fullmatch(slug):
        add_code(reject, "slug_invalid")
        finish(result, reject, hold)
        return result
    if any(article.get("slug") == slug for article in state["catalog"]["articles"]):
        add_code(reject, "slug_conflict")
        finish(result, reject, hold)
        return result
    day = shanghai_day(published_at)
    label = "知乎回答" if kind == "answer" else "知乎文章"
    source_label = "知乎原回答" if kind == "answer" else "知乎原文"
    entry = {
        "slug": slug,
        "content": f"content/{slug}.md",
        "section": "buzz",
        "title": title,
        "topic": label,
        "kicker": label,
        "deck": deck,
        "date": f"发布于 {day}",
        "datePublished": day,
        "source": {"label": source_label, "url": identity_url},
        "format": "markdown",
        "order": next_buzz_order(state["catalog"]),
    }
    ledger_item = {
        "kind": kind,
        "id": item_id,
        "question_id": item.get("question_id") if kind == "answer" else None,
        "canonical_url": identity_url,
        "slug": slug,
        "body_sha256": sha256_text(normalized),
        "approval_id": approval_id,
        "ingested_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    result["decision"] = "publish"
    result["reasons"] = []
    result["slug"] = slug
    result["_action"] = {
        "body": normalized,
        "entry": entry,
        "ledger_item": ledger_item,
        "release_hold_id": matched_hold.get("hold_id") if released_hold and matched_hold else None,
    }
    return result


def attach_slug(result: dict[str, Any], item_id: str | None, kind: str | None) -> dict[str, Any]:
    if isinstance(item_id, str) and kind in {"answer", "article"}:
        result["slug"] = f"zhihu-{kind}-{item_id}"
    return result


def finish(result: dict[str, Any], reject: list[str], hold: list[str], decision: str | None = None, reasons: list[str] | None = None) -> None:
    if decision == "skip" and not reject:
        result["decision"] = "skip"
        result["reasons"] = reasons or ["idempotent_duplicate"]
        return
    if reject:
        result["decision"] = "reject"
        result["reasons"] = reject
        return
    result["decision"] = "hold"
    result["reasons"] = hold or ["not_proven_after_baseline"]


def public_result(result: dict[str, Any]) -> dict[str, Any]:
    copied = dict(result)
    copied.pop("_action", None)
    copied["wrote"] = False
    return copied


def insert_buzz_article(catalog: dict[str, Any], entry: dict[str, Any]) -> None:
    articles = catalog["articles"]
    index = 0
    for position, article in enumerate(articles):
        if article.get("section") == "buzz":
            index = position + 1
    articles.insert(index, entry)


def apply_publish(root: Path, state: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    action = result["_action"]
    entry = action["entry"]
    relative = entry["content"]
    destination = (root / relative).resolve()
    content_root = (root / "content").resolve()
    if content_root not in destination.parents or destination.suffix != ".md":
        raise ZhihuIngestError("refusing to write outside content/")
    atomic_write(destination, action["body"])
    insert_buzz_article(state["catalog"], entry)
    write_json(catalog_path(root), state["catalog"])
    state["ledger"]["items"].append(action["ledger_item"])
    write_json(ledger_path(root), state["ledger"])
    release_id = action.get("release_hold_id")
    if release_id:
        move_hold_to_known(state["baseline"], release_id, entry["slug"])
        write_json(baseline_path(root), state["baseline"])
    public = public_result(result)
    public["wrote"] = True
    public["paths"] = [relative, "content/article-catalog.json", "scripts/zhihu-sync/ledger.json"]
    return public


def move_hold_to_known(baseline: dict[str, Any], hold_id: str, slug: str) -> None:
    remaining = []
    moved = None
    for hold in baseline["holds"]:
        if isinstance(hold, dict) and hold.get("hold_id") == hold_id:
            moved = hold
        else:
            remaining.append(hold)
    if moved is None:
        return
    baseline["holds"] = remaining
    baseline["known"].append(
        {
            "disposition": "already_on_site",
            "kind": moved.get("kind"),
            "id": moved.get("id"),
            "question_id": moved.get("question_id"),
            "canonical_url": moved.get("canonical_url"),
            "site_slug": slug,
        }
    )


def evaluate_manifest(root: Path, manifest: Any) -> dict[str, Any]:
    state = load_state(root)
    if "error" in state:
        return state["error"]
    return public_result(plan_manifest(manifest, state, root, mode="evaluate", cli_approval=None))


def ingest_manifest(root: Path, manifest: Any, cli_approval: str | None) -> dict[str, Any]:
    with project_lock(root):
        state = load_state(root)
        if "error" in state:
            return state["error"]
        planned = plan_manifest(manifest, state, root, mode="ingest", cli_approval=cli_approval)
        if planned["decision"] != "publish":
            return public_result(planned)
        return apply_publish(root, state, planned)


def csv_kind(value: str) -> tuple[str | None, str | None]:
    text = value.strip()
    if text in KIND_FROM_CSV:
        return KIND_FROM_CSV[text], None
    if text in OUT_OF_SCOPE_CSV:
        return None, "kind_out_of_scope"
    if text == "":
        return None, None
    return None, "kind_invalid"


def inspect_csv(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeError:
        return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["csv_encoding"], "rows": []}
    reader = csv.DictReader(raw.splitlines())
    fieldnames = list(reader.fieldnames or [])
    if fieldnames != list(CSV_COLUMNS):
        return {
            "schema_version": SCHEMA_VERSION,
            "decision": "reject",
            "reasons": ["csv_schema"],
            "rows": [],
            "unknown_fields": ["item.body_markdown", "provenance.collected_at", "provenance.published_at", "provenance.modified_at"],
        }
    rows = []
    for raw_row in reader:
        row = {key: raw_row.get(key, "") for key in CSV_COLUMNS}
        kind, kind_problem = csv_kind(row["type"])
        parsed = parse_canonical_url(row["url"].strip())
        observed_day = row["date"].strip()
        source_day = observed_day if DATE_ONLY.fullmatch(observed_day) else None
        reasons = [
            "collector_csv_insufficient",
            "missing_body",
            "published_at_unknown",
            "modified_at_unknown",
            "collected_at_unknown",
            "privacy_unreviewed",
            "approval_required",
            "comments_not_ingested",
            "time_source_not_exact",
        ]
        unknown_fields = [
            "item.body_markdown",
            "provenance.collected_at",
            "provenance.published_at",
            "provenance.modified_at",
            "privacy_clearance",
            "publish_approval",
        ]
        decision = "hold"
        if kind_problem == "kind_out_of_scope":
            decision = "reject"
            reasons = ["kind_out_of_scope", "comments_not_ingested"]
        elif kind_problem == "kind_invalid":
            decision = "reject"
            reasons = ["kind_invalid"]
        elif kind is None:
            add_code(unknown_fields, "item.kind")
            add_code(reasons, "identity_incomplete")
        if parsed is None:
            add_code(unknown_fields, "item.canonical_url")
            add_code(unknown_fields, "item.id")
            if decision != "reject":
                add_code(reasons, "canonical_url_not_exact")
        if source_day is None:
            add_code(unknown_fields, "provenance.source_day")
        identity = {
            "kind": kind,
            "id": None if parsed is None else parsed["id"],
            "canonical_url": None if parsed is None else parsed["canonical_url"],
        }
        if parsed is not None and kind is not None and parsed["kind"] != kind:
            decision = "reject"
            add_code(reasons, "canonical_url_mismatch")
        rows.append(
            {
                "decision": decision,
                "reasons": reasons,
                "unknown_fields": unknown_fields,
                "identity": identity,
                "source_day": source_day,
                "published_at": None,
                "modified_at": None,
                "collected_at": None,
                "wrote": False,
            }
        )
    if not rows:
        return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["csv_empty"], "rows": []}
    if any(row["decision"] == "reject" for row in rows):
        summary = "reject"
    elif any(row["decision"] == "hold" for row in rows):
        summary = "hold"
    else:
        summary = "skip"
    return {"schema_version": SCHEMA_VERSION, "decision": summary, "source": "collector_csv", "rows": rows}


def register_hold_identity(root: Path, hold_id: str, kind: str, item_id: str, question_id: str | None, url: str) -> dict[str, Any]:
    parsed = parse_canonical_url(url)
    if kind not in {"answer", "article"} or not ID_TEXT.fullmatch(item_id) or parsed is None:
        return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["identity_incomplete"], "wrote": False}
    if parsed["kind"] != kind or parsed["id"] != item_id:
        return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["canonical_url_mismatch"], "wrote": False}
    if kind == "answer":
        if question_id is None or not ID_TEXT.fullmatch(question_id) or parsed["question_id"] != question_id:
            return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["identity_incomplete"], "wrote": False}
    with project_lock(root):
        state = load_state(root)
        if "error" in state:
            return state["error"]
        hold = next((entry for entry in state["baseline"]["holds"] if entry.get("hold_id") == hold_id), None)
        if hold is None:
            return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["hold_not_found"], "wrote": False}
        if hold.get("disposition") != "held_pending_confirmation":
            return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["hold_not_pending"], "wrote": False}
        if hold.get("kind") not in (None, kind):
            return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["canonical_url_mismatch"], "wrote": False}
        for field, value in (("id", item_id), ("canonical_url", url)):
            current = hold.get(field)
            if current not in (None, value):
                return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["identity_conflict"], "wrote": False}
        if kind == "answer" and hold.get("question_id") not in (None, question_id):
            return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["identity_conflict"], "wrote": False}
        unchanged = hold.get("id") == item_id and hold.get("canonical_url") == url
        hold["kind"] = kind
        hold["id"] = item_id
        hold["canonical_url"] = url
        if kind == "answer":
            hold["question_id"] = question_id
        reasons = [reason for reason in hold.get("hold_reasons", []) if reason != "canonical_identity_incomplete"]
        if "explicit_confirmation_required" not in reasons:
            reasons.append("explicit_confirmation_required")
        hold["hold_reasons"] = reasons
        hold["disposition"] = "held_pending_confirmation"
        if not unchanged:
            write_json(baseline_path(root), state["baseline"])
        return {
            "schema_version": SCHEMA_VERSION,
            "decision": "skip" if unchanged else "identity_registered",
            "reasons": ["explicit_confirmation_required"],
            "identity": {"kind": kind, "id": item_id, "canonical_url": url},
            "wrote": not unchanged,
        }


def release_hold(root: Path, hold_id: str, token: str) -> dict[str, Any]:
    if not CONFIRM_TOKEN.fullmatch(token):
        return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["confirmation_invalid"], "wrote": False}
    with project_lock(root):
        state = load_state(root)
        if "error" in state:
            return state["error"]
        hold = next((entry for entry in state["baseline"]["holds"] if entry.get("hold_id") == hold_id), None)
        if hold is None:
            return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["hold_not_found"], "wrote": False}
        if not hold.get("id") or not hold.get("canonical_url"):
            return {
                "schema_version": SCHEMA_VERSION,
                "decision": "hold",
                "reasons": ["canonical_identity_incomplete", "explicit_confirmation_required"],
                "wrote": False,
            }
        confirmation = hold.get("confirmation")
        if isinstance(confirmation, dict) and confirmation.get("token") == token:
            return {
                "schema_version": SCHEMA_VERSION,
                "decision": "skip",
                "reasons": ["confirmation_already_recorded"],
                "wrote": False,
            }
        if isinstance(confirmation, dict):
            return {"schema_version": SCHEMA_VERSION, "decision": "reject", "reasons": ["confirmation_conflict"], "wrote": False}
        hold["confirmation"] = {
            "token": token,
            "confirmed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        hold["disposition"] = "held_pending_confirmation"
        write_json(baseline_path(root), state["baseline"])
        return {
            "schema_version": SCHEMA_VERSION,
            "decision": "confirmation_recorded",
            "reasons": ["explicit_confirmation_required"],
            "wrote": True,
            "publishes": False,
        }


def exit_code(result: dict[str, Any]) -> int:
    decision = result.get("decision")
    if decision in {"publish", "eligible", "skip", "identity_registered", "confirmation_recorded"}:
        return EXIT_OK
    if decision == "hold":
        return EXIT_HOLD
    if decision == "reject":
        return EXIT_REJECT
    return EXIT_ERROR


def emit(result: dict[str, Any]) -> int:
    sys.stdout.write(json_ready(result))
    return exit_code(result)


def read_manifest(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"__invalid_json__": True}


def command_manifest(root: Path, path: Path, ingest: bool, approve: str | None) -> dict[str, Any]:
    loaded = read_manifest(path)
    if isinstance(loaded, dict) and loaded.get("__invalid_json__"):
        result = blank_result()
        result["reasons"] = ["invalid_json"]
        return result
    if ingest:
        return ingest_manifest(root, loaded, approve)
    return evaluate_manifest(root, loaded)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="把未来新的知乎回答或文章，经独立隐私放行和显式批准后写入炒作目录。")
    parser.add_argument("--root", type=Path, default=None, help="网站仓库根目录，默认是本脚本所在仓库")
    commands = parser.add_subparsers(dest="command", required=True)

    evaluate = commands.add_parser("evaluate", help="只判断，不写正文")
    evaluate.add_argument("--manifest", type=Path, required=True)

    ingest = commands.add_parser("ingest", help="在显式批准后写入一篇")
    ingest.add_argument("--manifest", type=Path, required=True)
    ingest.add_argument("--approve", default=None, help="必须与清单里的 approval_id 相同才会写入")

    inspect = commands.add_parser("inspect-csv", help="说明现有采集 CSV 为什么不能上站")
    inspect.add_argument("--csv", type=Path, required=True)

    register = commands.add_parser("register-hold-identity", help="只补齐暂扣条目缺失的公开身份，不放行、不写正文")
    register.add_argument("--hold-id", required=True)
    register.add_argument("--kind", required=True, choices=("answer", "article"))
    register.add_argument("--id", required=True)
    register.add_argument("--question-id")
    register.add_argument("--url", required=True)

    release = commands.add_parser("release-hold", help="记录人工确认。确认本身不会上站。")
    release.add_argument("--hold-id", required=True)
    release.add_argument("--confirm", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = (args.root or repo_root_from_script()).resolve()
    try:
        if args.command == "evaluate":
            result = command_manifest(root, args.manifest, ingest=False, approve=None)
        elif args.command == "ingest":
            result = command_manifest(root, args.manifest, ingest=True, approve=args.approve)
        elif args.command == "inspect-csv":
            result = inspect_csv(args.csv)
        elif args.command == "register-hold-identity":
            result = register_hold_identity(root, args.hold_id, args.kind, args.id, args.question_id, args.url)
        elif args.command == "release-hold":
            result = release_hold(root, args.hold_id, args.confirm)
        else:
            result = blank_result()
            result["reasons"] = ["unknown_command"]
    except ZhihuIngestError as error:
        sys.stderr.write(f"{error}\n")
        return EXIT_ERROR
    return emit(result)


if __name__ == "__main__":
    sys.exit(main())
