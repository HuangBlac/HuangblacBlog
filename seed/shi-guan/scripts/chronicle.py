from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qsl, urlsplit


SCHEMA_VERSION = 1
EVENT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BRANCH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
WINDOWS_ABSOLUTE_PATH = re.compile(r"(?i)\b[a-z]:[\\/]")
WINDOWS_UNC_PATH = re.compile(
    r"(?i)(?<![a-z0-9])\\\\(?:(?:\?|\.)\\)?(?:UNC\\)?[^\\/\s]+[\\/][^\\/\s]+"
)
UNIX_ABSOLUTE_PATH = re.compile(
    r"(?<![a-zA-Z0-9:])/(?:Users|home|root|tmp|var|etc|mnt|media|opt|srv|Volumes)(?:/|$)"
)
FILE_URL = re.compile(r"(?i)\bfile:/+")
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
VISIBILITIES = {"private", "public"}
WINDOWS_RESERVED_NAMES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
EVIDENCE_TYPES = {
    "git_commit",
    "repo_file",
    "public_url",
    "user_statement",
    "issue",
    "pull_request",
    "release",
}


class ChronicleError(ValueError):
    """Raised when chronicle data would violate the storage contract."""


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _write_text_atomic(path: Path, content: str) -> None:
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


def _write_json_atomic(path: Path, value: Any) -> None:
    _write_text_atomic(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )


@contextmanager
def _project_lock(
    project_dir: Path,
    timeout_seconds: float = 5.0,
    *,
    lock_name: str = ".write.lock",
) -> Iterator[None]:
    project_dir.mkdir(parents=True, exist_ok=True)
    lock_path = project_dir / lock_name
    deadline = time.monotonic() + timeout_seconds
    descriptor: int | None = None
    token = uuid.uuid4().hex
    while descriptor is None:
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise ChronicleError(
                    f"项目写锁仍被占用：{project_dir.name}。若确认没有史官进程运行，"
                    f"请人工删除 {lock_name} 后重试"
                )
            time.sleep(0.05)
    try:
        os.write(descriptor, f"{os.getpid()}:{token}".encode("ascii"))
        os.close(descriptor)
        descriptor = None
        yield
    finally:
        if descriptor is not None:
            os.close(descriptor)
        try:
            if lock_path.read_text(encoding="ascii") == f"{os.getpid()}:{token}":
                lock_path.unlink()
        except FileNotFoundError:
            pass


def _store_root(seed_dir: Path | str) -> Path:
    seed_path = Path(seed_dir).resolve()
    store_path = seed_path / ".shi-guan"
    if not store_path.resolve().is_relative_to(seed_path):
        raise ChronicleError("史官数据目录不得通过链接离开 seed")
    return store_path


def _project_dir(seed_dir: Path | str, project_id: str) -> Path:
    _require_identifier(project_id, "project_id")
    store_path = _store_root(seed_dir)
    project_path = store_path / "projects" / project_id
    if not project_path.resolve().is_relative_to(store_path.resolve()):
        raise ChronicleError("项目数据目录不得通过链接离开史官仓库")
    return project_path


def _manifest_path(seed_dir: Path | str, project_id: str) -> Path:
    return _project_dir(seed_dir, project_id) / "manifest.json"


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise ChronicleError(f"缺少文件：{path.name}")
    try:
        return _strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ChronicleError) as error:
        raise ChronicleError(f"JSON 格式错误：{path.name}: {error}") from error


def _strict_json_loads(content: str) -> Any:
    def reject_constant(value: str) -> None:
        raise ChronicleError(f"JSON 不允许非有限数值：{value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ChronicleError(f"JSON 对象包含重复字段：{key}")
            result[key] = value
        return result

    return json.loads(
        content,
        parse_constant=reject_constant,
        object_pairs_hook=reject_duplicate_keys,
    )


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or not EVENT_ID_PATTERN.fullmatch(value):
        raise ChronicleError(f"{label} 必须使用小写字母、数字、点、下划线或连字符")
    if len(value) > 128:
        raise ChronicleError(f"{label} 不能超过 128 个字符")
    if value.casefold() in WINDOWS_RESERVED_NAMES:
        raise ChronicleError(f"{label} 不能使用系统保留名")


def _require_single_line(value: Any, label: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChronicleError(f"{label} 不能为空")
    cleaned = value.strip()
    if "\n" in cleaned or "\r" in cleaned or CONTROL_CHARACTERS.search(cleaned):
        raise ChronicleError(f"{label} 必须是无控制字符的单行文本")
    if len(cleaned) > maximum:
        raise ChronicleError(f"{label} 不能超过 {maximum} 个字符")
    return cleaned


def _require_safe_text(value: Any, label: str, *, maximum: int = 10_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChronicleError(f"{label} 不能为空")
    cleaned = value.strip()
    if CONTROL_CHARACTERS.search(cleaned):
        raise ChronicleError(f"{label} 含控制字符")
    if len(cleaned) > maximum:
        raise ChronicleError(f"{label} 不能超过 {maximum} 个字符")
    return cleaned


def _contains_local_absolute_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            _contains_local_absolute_path(item)
            for pair in value.items()
            for item in pair
        )
    if isinstance(value, list):
        return any(_contains_local_absolute_path(item) for item in value)
    if not isinstance(value, str):
        return False
    return bool(
        WINDOWS_ABSOLUTE_PATH.search(value)
        or WINDOWS_UNC_PATH.search(value)
        or UNIX_ABSOLUTE_PATH.search(value)
        or FILE_URL.search(value)
    )


def _normalise_remote(remote: str) -> str:
    value = remote.strip().replace("\\", "/")
    if value.endswith(".git"):
        value = value[:-4]
    return value.rstrip("/").lower()


def _validate_remote(remote: str) -> None:
    if not remote:
        return
    _require_single_line(remote, "remote", maximum=2_000)
    if "@" in remote and "://" in remote:
        parsed = urlsplit(remote)
        if parsed.username or parsed.password:
            raise ChronicleError("remote 不得包含用户名或密码")
    if "?" in remote or "#" in remote:
        raise ChronicleError("remote 不得包含查询参数或片段")


def _validate_public_url(reference: str) -> None:
    _require_single_line(reference, "public_url.ref", maximum=2_000)
    parsed = urlsplit(reference)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ChronicleError("public_url.ref 必须是完整 HTTPS URL")
    if parsed.username or parsed.password:
        raise ChronicleError("public_url.ref 不得包含凭据")
    sensitive_keys = {"access_token", "api_key", "apikey", "key", "secret", "token"}
    if any(key.casefold() in sensitive_keys for key, _ in parse_qsl(parsed.query)):
        raise ChronicleError("public_url.ref 不得包含敏感查询参数")


def _chronicle_filename(project_name: str) -> str:
    forbidden = '<>:"/\\|?*'
    cleaned = "".join("_" if character in forbidden else character for character in project_name)
    cleaned = cleaned.strip().rstrip(".")
    if not cleaned:
        raise ChronicleError("project_name 不能生成空文件名")
    return f"{cleaned}传.md"


def _normalise_output_name(filename: str) -> str:
    return unicodedata.normalize("NFKC", filename).casefold().rstrip(". ")


def _validate_manifest(manifest: Any, project_id: str, seed_path: Path) -> None:
    if not isinstance(manifest, dict):
        raise ChronicleError("manifest 必须是对象")
    required = {
        "schema_version",
        "project_id",
        "project_name",
        "remote",
        "remote_fingerprint",
        "visibility",
        "chronicle_file",
        "project_summary",
        "created_on",
    }
    missing = sorted(required - set(manifest))
    if missing:
        raise ChronicleError("manifest 缺少字段：" + ", ".join(missing))
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise ChronicleError(f"manifest 只支持 schema_version={SCHEMA_VERSION}")
    _require_identifier(manifest["project_id"], "manifest.project_id")
    if manifest["project_id"] != project_id:
        raise ChronicleError("manifest project_id 不一致")
    project_name = _require_single_line(manifest["project_name"], "project_name", maximum=120)
    _validate_remote(manifest["remote"])
    expected_fingerprint = hashlib.sha256(
        _normalise_remote(manifest["remote"]).encode("utf-8")
    ).hexdigest()
    if manifest["remote_fingerprint"] != expected_fingerprint:
        raise ChronicleError("manifest remote_fingerprint 不一致")
    if manifest["visibility"] not in VISIBILITIES:
        raise ChronicleError("manifest visibility 非法")
    if not isinstance(manifest["project_summary"], str):
        raise ChronicleError("project_summary 必须是字符串")
    if manifest["project_summary"]:
        _require_safe_text(manifest["project_summary"], "project_summary")
    if not DATE_PATTERN.fullmatch(str(manifest["created_on"])):
        raise ChronicleError("manifest created_on 必须是 YYYY-MM-DD")
    try:
        date.fromisoformat(manifest["created_on"])
    except ValueError as error:
        raise ChronicleError("manifest created_on 不是有效日期") from error

    expected_filename = _chronicle_filename(project_name)
    if manifest["chronicle_file"] != expected_filename:
        raise ChronicleError("manifest chronicle_file 与 project_name 不一致")
    output_path = (seed_path / expected_filename).resolve()
    if output_path.parent != seed_path or output_path.suffix.casefold() != ".md":
        raise ChronicleError("传记输出必须是 seed 根目录内的 Markdown 文件")
    if _contains_local_absolute_path(manifest):
        raise ChronicleError("manifest 含本地绝对路径")


def _validate_state(state: Any, project_id: str, events: list[dict[str, Any]]) -> None:
    if not isinstance(state, dict):
        raise ChronicleError("state 必须是对象")
    required = {"schema_version", "project_id", "last_commit", "last_event_id"}
    missing = sorted(required - set(state))
    if missing:
        raise ChronicleError("state 缺少字段：" + ", ".join(missing))
    if state["schema_version"] != SCHEMA_VERSION or state["project_id"] != project_id:
        raise ChronicleError("state 版本或 project_id 不一致")
    last_commit = state["last_commit"]
    last_event_id = state["last_event_id"]
    if last_commit is not None and (
        not isinstance(last_commit, str) or not GIT_SHA_PATTERN.fullmatch(last_commit)
    ):
        raise ChronicleError("state.last_commit 必须是完整 Git SHA 或 null")
    if last_event_id is not None:
        _require_identifier(last_event_id, "state.last_event_id")
        by_id = {event.get("event_id"): event for event in events}
        if last_event_id not in by_id:
            raise ChronicleError("state.last_event_id 不在事件库中")
        if last_commit is not None:
            git_refs = {
                evidence.get("ref")
                for evidence in by_id[last_event_id].get("evidence", [])
                if evidence.get("type") == "git_commit"
            }
            if last_commit not in git_refs:
                raise ChronicleError("state.last_commit 不属于 last_event_id 的 Git 证据")
    elif last_commit is not None:
        raise ChronicleError("state.last_commit 存在时 last_event_id 不能为 null")


def init_project(
    seed_dir: Path | str,
    *,
    project_id: str,
    project_name: str,
    remote: str,
    visibility: str,
    project_summary: str = "",
) -> Path:
    _require_identifier(project_id, "project_id")
    project_name = _require_single_line(project_name, "project_name", maximum=120)
    _validate_remote(remote)
    if project_summary:
        _require_safe_text(project_summary, "project_summary")
    if visibility not in VISIBILITIES:
        raise ChronicleError(f"visibility 必须是 {sorted(VISIBILITIES)} 之一")
    if _contains_local_absolute_path(
        {"name": project_name, "remote": remote, "summary": project_summary}
    ):
        raise ChronicleError("项目清单不得包含本地绝对路径")

    seed_path = Path(seed_dir).resolve()
    store_path = _store_root(seed_path)
    projects_path = store_path / "projects"
    projects_path.mkdir(parents=True, exist_ok=True)
    project_dir = _project_dir(seed_path, project_id)
    chronicle_file = _chronicle_filename(project_name)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "project_id": project_id,
        "project_name": project_name,
        "remote": remote.strip(),
        "remote_fingerprint": hashlib.sha256(
            _normalise_remote(remote).encode("utf-8")
        ).hexdigest(),
        "visibility": visibility,
        "chronicle_file": chronicle_file,
        "project_summary": project_summary.strip(),
        "created_on": date.today().isoformat(),
    }

    with _project_lock(store_path, lock_name=".registry.lock"):
        wanted_name = _normalise_output_name(chronicle_file)
        for existing_id in _iter_project_ids(seed_path):
            if existing_id == project_id:
                continue
            existing_manifest = _load_json(_manifest_path(seed_path, existing_id))
            if _normalise_output_name(existing_manifest.get("chronicle_file", "")) == wanted_name:
                raise ChronicleError(
                    f"传记文件名已由项目 {existing_id} 使用：{chronicle_file}"
                )

        project_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = project_dir / "manifest.json"
        with _project_lock(project_dir):
            if manifest_path.exists():
                existing = _load_json(manifest_path)
                _validate_manifest(existing, project_id, seed_path)
                identity_fields = ("project_id", "project_name", "remote_fingerprint")
                if any(existing.get(field) != manifest[field] for field in identity_fields):
                    raise ChronicleError("项目已注册，但名称或远端指纹不一致")
                manifest = existing
            else:
                _write_json_atomic(manifest_path, manifest)

            state_path = project_dir / "state.json"
            if not state_path.exists():
                _write_json_atomic(
                    state_path,
                    {
                        "schema_version": SCHEMA_VERSION,
                        "project_id": project_id,
                        "last_commit": None,
                        "last_event_id": None,
                    },
                )
            events_path = project_dir / "events.jsonl"
            if not events_path.exists():
                _write_text_atomic(events_path, "")

            _validate_manifest(manifest, project_id, seed_path)
            events = load_events(seed_path, project_id)
            state = _load_json(state_path)
            _validate_state(state, project_id, events)
            _render_chronicle_unlocked(seed_path, project_id, manifest, events)

    return seed_path / str(manifest["chronicle_file"])


def _validate_event(event: dict[str, Any], project_id: str) -> None:
    required = {
        "schema_version",
        "event_id",
        "project_id",
        "occurred_on",
        "title",
        "summary",
        "facts",
        "evidence",
        "tags",
        "visibility",
        "zhihu_angles",
        "supersedes",
        "retracts",
    }
    missing = sorted(required - set(event))
    if missing:
        raise ChronicleError(f"事件缺少字段：{', '.join(missing)}")
    if event["schema_version"] != SCHEMA_VERSION:
        raise ChronicleError(f"只支持 schema_version={SCHEMA_VERSION}")
    _require_identifier(event["event_id"], "event_id")
    _require_identifier(event["project_id"], "project_id")
    if event["project_id"] != project_id:
        raise ChronicleError("事件 project_id 与目标项目不一致")
    if not isinstance(event["occurred_on"], str) or not DATE_PATTERN.fullmatch(
        event["occurred_on"]
    ):
        raise ChronicleError("occurred_on 必须是 YYYY-MM-DD")
    try:
        date.fromisoformat(event["occurred_on"])
    except (TypeError, ValueError) as error:
        raise ChronicleError("occurred_on 必须是 YYYY-MM-DD") from error
    _require_single_line(event["title"], "title", maximum=200)
    _require_safe_text(event["summary"], "summary")
    if event["visibility"] not in VISIBILITIES:
        raise ChronicleError(f"visibility 必须是 {sorted(VISIBILITIES)} 之一")
    for field in ("facts", "evidence", "tags", "zhihu_angles", "supersedes", "retracts"):
        if not isinstance(event[field], list):
            raise ChronicleError(f"{field} 必须是数组")
    if not event["facts"] or not event["evidence"]:
        raise ChronicleError("每个事件至少需要一条事实和一份证据")
    if not event["tags"]:
        raise ChronicleError("每个事件至少需要一个检索标签")
    for field in ("tags", "zhihu_angles", "supersedes", "retracts"):
        if any(not isinstance(value, str) or not value.strip() for value in event[field]):
            raise ChronicleError(f"{field} 只能包含非空字符串")
    for value in event["tags"]:
        _require_single_line(value, "tag", maximum=100)
    for value in event["zhihu_angles"]:
        _require_safe_text(value, "zhihu_angle", maximum=1_000)
    normalised_tags = [value.strip().casefold() for value in event["tags"]]
    if len(normalised_tags) != len(set(normalised_tags)):
        raise ChronicleError("tags 忽略大小写和首尾空格后不得重复")
    if len(event["supersedes"]) != len(set(event["supersedes"])):
        raise ChronicleError("supersedes 不得重复")
    if len(event["retracts"]) != len(set(event["retracts"])):
        raise ChronicleError("retracts 不得重复")
    overlap = set(event["supersedes"]) & set(event["retracts"])
    if overlap:
        raise ChronicleError("同一事件不能同时被替代和撤回")

    evidence_ids: set[str] = set()
    for evidence in event["evidence"]:
        if not isinstance(evidence, dict):
            raise ChronicleError("evidence 条目必须是对象")
        for field in ("id", "type", "ref", "label"):
            if not isinstance(evidence.get(field), str) or not evidence[field].strip():
                raise ChronicleError(f"evidence.{field} 不能为空")
        _require_single_line(evidence["id"], "evidence.id", maximum=300)
        _require_single_line(evidence["type"], "evidence.type", maximum=50)
        _require_single_line(evidence["ref"], "evidence.ref", maximum=2_000)
        _require_single_line(evidence["label"], "evidence.label", maximum=500)
        if evidence["type"] not in EVIDENCE_TYPES:
            raise ChronicleError(f"未知 evidence.type：{evidence['type']}")
        if evidence["type"] == "git_commit":
            if not GIT_SHA_PATTERN.fullmatch(evidence["ref"]):
                raise ChronicleError("git_commit.ref 必须是完整的小写 Git SHA")
            if evidence["id"] != f"git:{evidence['ref']}":
                raise ChronicleError("git_commit.id 必须等于 git:<ref>")
        elif evidence["type"] == "public_url":
            _validate_public_url(evidence["ref"])
        if evidence["id"] in evidence_ids:
            raise ChronicleError(f"证据 ID 重复：{evidence['id']}")
        evidence_ids.add(evidence["id"])

    for fact in event["facts"]:
        if (
            not isinstance(fact, dict)
            or not isinstance(fact.get("statement"), str)
            or not fact["statement"].strip()
        ):
            raise ChronicleError("facts 条目必须包含 statement")
        references = fact.get("evidence_ids")
        if not isinstance(references, list) or not references:
            raise ChronicleError("每条事实至少引用一个 evidence_id")
        if any(not isinstance(reference, str) or not reference.strip() for reference in references):
            raise ChronicleError("facts.evidence_ids 只能包含非空字符串")
        if len(references) != len(set(references)):
            raise ChronicleError("facts.evidence_ids 不得重复")
        _require_safe_text(fact["statement"], "fact.statement")
        unknown = set(references) - evidence_ids
        if unknown:
            raise ChronicleError(f"事实引用了未知证据：{', '.join(sorted(unknown))}")

    for relation in ("supersedes", "retracts"):
        for target in event[relation]:
            _require_identifier(target, f"{relation} target")
            if target == event["event_id"]:
                raise ChronicleError(f"事件不能 {relation} 自己")

    commentary = event.get("commentary")
    if commentary is not None:
        if not isinstance(commentary, dict):
            raise ChronicleError("commentary 必须是对象")
        if commentary.get("label") != "太史公曰":
            raise ChronicleError("评论层的 label 必须是“太史公曰”")
        _require_safe_text(commentary.get("text"), "太史公曰")
        if commentary.get("visibility") not in VISIBILITIES:
            raise ChronicleError("太史公曰必须声明 visibility")
        if event["visibility"] == "private" and commentary["visibility"] == "public":
            raise ChronicleError("太史公曰不能比事件本身更公开")
        based_on = commentary.get("based_on")
        if not isinstance(based_on, list) or not based_on:
            raise ChronicleError("太史公曰必须声明 based_on")
        if any(not isinstance(value, str) or not value.strip() for value in based_on):
            raise ChronicleError("commentary.based_on 只能包含非空事件 ID")
        if len(based_on) != len(set(based_on)):
            raise ChronicleError("commentary.based_on 不得重复")
        for target in based_on:
            _require_identifier(target, "commentary.based_on")

    if _contains_local_absolute_path(event):
        raise ChronicleError("事件不得包含本地绝对路径")


def load_events(seed_dir: Path | str, project_id: str) -> list[dict[str, Any]]:
    path = _project_dir(seed_dir, project_id) / "events.jsonl"
    if not path.is_file():
        raise ChronicleError(f"项目尚未初始化：{project_id}")
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise ChronicleError(f"无法读取 events.jsonl：{error}") from error
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            raise ChronicleError(f"events.jsonl 第 {line_number} 行为空")
        try:
            event = _strict_json_loads(line)
        except (json.JSONDecodeError, ChronicleError) as error:
            raise ChronicleError(f"events.jsonl 第 {line_number} 行格式错误") from error
        if not isinstance(event, dict):
            raise ChronicleError(f"events.jsonl 第 {line_number} 行必须是对象")
        events.append(event)
    return events


def append_event(
    seed_dir: Path | str,
    project_id: str,
    event: dict[str, Any],
    *,
    cursor: str | None = None,
) -> bool:
    project_dir = _project_dir(seed_dir, project_id)
    seed_path = Path(seed_dir).resolve()
    manifest = _load_json(project_dir / "manifest.json")
    _validate_manifest(manifest, project_id, seed_path)
    _validate_event(event, project_id)
    if manifest["visibility"] == "public" and event["visibility"] != "public":
        raise ChronicleError("公开项目传不能写入 private 事件")
    if (
        manifest["visibility"] == "public"
        and event.get("commentary", {}).get("visibility") == "private"
    ):
        raise ChronicleError("公开项目传不能写入 private 太史公曰")
    if cursor is not None:
        if not isinstance(cursor, str) or not GIT_SHA_PATTERN.fullmatch(cursor):
            raise ChronicleError("cursor 必须是完整的小写 Git SHA")
        event_git_refs = {
            evidence["ref"]
            for evidence in event["evidence"]
            if evidence["type"] == "git_commit"
        }
        if cursor not in event_git_refs:
            raise ChronicleError("cursor 必须属于本事件的 Git 证据")

    added = False
    with _project_lock(project_dir):
        events = load_events(seed_dir, project_id)
        state = _load_json(project_dir / "state.json")
        _validate_state(state, project_id, events)
        by_id = {item["event_id"]: item for item in events}
        existing = by_id.get(event["event_id"])
        if existing is not None:
            if _json_text(existing) != _json_text(event):
                raise ChronicleError(f"event_id 已存在但内容不同：{event['event_id']}")
            if cursor is not None and state.get("last_commit") != cursor:
                if events[-1]["event_id"] != event["event_id"]:
                    if state.get("last_commit") is None:
                        raise ChronicleError("只能为事件库最后一条事件恢复 Git 游标")
                else:
                    previous_event_ids = {
                        item["event_id"] for item in events[:-1]
                    }
                    state_points_to_previous_event = (
                        state.get("last_event_id") in previous_event_ids
                        or (
                            state.get("last_event_id") is None
                            and state.get("last_commit") is None
                        )
                    )
                    if state_points_to_previous_event:
                        _advance_state(project_dir, event["event_id"], cursor)
        else:
            existing_evidence = {
                evidence["id"]: item["event_id"]
                for item in events
                for evidence in item["evidence"]
            }
            reused = {
                evidence["id"]: existing_evidence[evidence["id"]]
                for evidence in event["evidence"]
                if evidence["id"] in existing_evidence
            }
            if reused:
                details = ", ".join(
                    f"{key}（已见于 {value}）" for key, value in reused.items()
                )
                raise ChronicleError(f"证据已经写入其他事件：{details}")

            known_ids = set(by_id)
            for relation in ("supersedes", "retracts"):
                unknown = set(event[relation]) - known_ids
                if unknown:
                    raise ChronicleError(
                        f"{relation} 引用了尚不存在的事件：{', '.join(sorted(unknown))}"
                    )

            commentary = event.get("commentary")
            if commentary:
                allowed_commentary_ids = known_ids | {event["event_id"]}
                unknown = set(commentary["based_on"]) - allowed_commentary_ids
                if unknown:
                    raise ChronicleError(
                        "太史公曰引用了未知或未来事件：" + ", ".join(sorted(unknown))
                    )

            already_transitioned = {
                target
                for item in events
                for relation in ("supersedes", "retracts")
                for target in item[relation]
            }
            transitioning = set(event["supersedes"]) | set(event["retracts"])
            repeated_transition = transitioning & already_transitioned
            if repeated_transition:
                raise ChronicleError(
                    "事件已经被修订过：" + ", ".join(sorted(repeated_transition))
                )

            events.append(event)
            content = "".join(_json_text(item) + "\n" for item in events)
            _write_text_atomic(project_dir / "events.jsonl", content)
            _advance_state(project_dir, event["event_id"], cursor)
            added = True

        _render_chronicle_unlocked(seed_path, project_id, manifest, events)

    return added


def _advance_state(project_dir: Path, event_id: str, cursor: str | None) -> None:
    if cursor is None:
        return
    state_path = project_dir / "state.json"
    state = _load_json(state_path)
    state["last_event_id"] = event_id
    state["last_commit"] = cursor
    _write_json_atomic(state_path, state)


def _run_git(repository: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        message = getattr(error, "stderr", "") or str(error)
        raise ChronicleError(f"无法读取 Git 历史：{message.strip()}") from error
    return result.stdout.strip()


def scan_git_commits(
    seed_dir: Path | str,
    project_id: str,
    repository: Path | str,
    *,
    branch: str = "HEAD",
) -> list[dict[str, str]]:
    if not isinstance(branch, str) or not BRANCH_PATTERN.fullmatch(branch):
        raise ChronicleError("branch 不是安全的 Git 引用名")
    if ".." in branch or "//" in branch or branch.endswith(("/", ".")):
        raise ChronicleError("branch 不是安全的 Git 引用名")
    repository_path = Path(repository).resolve()
    manifest = _load_json(_manifest_path(seed_dir, project_id))
    seed_path = Path(seed_dir).resolve()
    _validate_manifest(manifest, project_id, seed_path)
    events = load_events(seed_path, project_id)
    state = _load_json(_project_dir(seed_path, project_id) / "state.json")
    _validate_state(state, project_id, events)
    if _run_git(repository_path, "rev-parse", "--is-inside-work-tree") != "true":
        raise ChronicleError("目标目录不是 Git 仓库")

    expected = _normalise_remote(manifest.get("remote", ""))
    if expected:
        actual = _normalise_remote(_run_git(repository_path, "remote", "get-url", "origin"))
        if actual != expected:
            raise ChronicleError("Git origin 与项目清单不一致")

    try:
        branch_commit = _run_git(
            repository_path,
            "rev-parse",
            "--verify",
            "--end-of-options",
            f"{branch}^{{commit}}",
        )
    except ChronicleError as error:
        raise ChronicleError(f"找不到 Git 分支或提交：{branch}") from error
    if not GIT_SHA_PATTERN.fullmatch(branch_commit):
        raise ChronicleError("Git 未返回完整提交 SHA")

    last_commit = state.get("last_commit")
    revision_range = f"{last_commit}..{branch_commit}" if last_commit else branch_commit
    if last_commit:
        try:
            _run_git(repository_path, "cat-file", "-e", f"{last_commit}^{{commit}}")
            _run_git(
                repository_path,
                "merge-base",
                "--is-ancestor",
                last_commit,
                branch_commit,
            )
        except ChronicleError as error:
            raise ChronicleError("上次扫描游标不在目标分支历史中，请人工校正") from error

    field_separator = "\x1f"
    record_separator = "\x1e"
    output = _run_git(
        repository_path,
        "log",
        "--reverse",
        "--no-merges",
        "--format=%H%x1f%cs%x1f%an%x1f%s%x1e",
        revision_range,
    )
    candidates: list[dict[str, str]] = []
    for record in output.split(record_separator):
        record = record.strip("\r\n ")
        if not record:
            continue
        parts = record.split(field_separator, 3)
        if len(parts) != 4:
            raise ChronicleError("Git 日志输出无法解析")
        commit, occurred_on, author, subject = parts
        candidates.append(
            {
                "commit": commit,
                "occurred_on": occurred_on,
                "author": author,
                "subject": subject,
                "evidence_id": f"git:{commit}",
            }
        )
    return candidates


def _event_statuses(events: list[dict[str, Any]]) -> dict[str, str]:
    statuses = {event["event_id"]: "active" for event in events}
    for event in events:
        for target in event.get("supersedes", []):
            statuses[target] = "superseded"
        for target in event.get("retracts", []):
            statuses[target] = "retracted"
    return statuses


def _render_evidence(evidence: dict[str, str]) -> str:
    reference = evidence["ref"]
    if evidence["type"] == "public_url" and reference.startswith("https://"):
        reference = f"[{evidence['label']}]({reference})"
        return f"- `{evidence['id']}` · {reference}"
    return f"- `{evidence['id']}` · {evidence['label']} · `{reference}`"


def _render_chronicle_unlocked(
    seed_path: Path,
    project_id: str,
    manifest: dict[str, Any],
    events: list[dict[str, Any]],
) -> Path:
    _validate_manifest(manifest, project_id, seed_path)
    statuses = _event_statuses(events)

    lines = [
        f"# {manifest['project_name']}传",
        "",
        "> 本传记录经过证据支持的项目事件。事实、文章角度与史官评论分开保存；评论不反向充当事实。",
        "",
    ]
    if manifest.get("project_summary"):
        lines.extend([manifest["project_summary"], ""])
    lines.extend(
        [
            f"- 项目标识　`{manifest['project_id']}`",
            f"- 公开级别　`{manifest['visibility']}`",
            f"- 远端来源　{manifest['remote'] or '未登记'}",
            "",
        ]
    )
    if not events:
        lines.extend(["## 纪事", "", "尚无正式事件。", ""])
    else:
        for event in sorted(events, key=lambda item: item["occurred_on"]):
            lines.extend([f"## {event['occurred_on']}　{event['title']}", ""])
            status = statuses[event["event_id"]]
            if status == "superseded":
                lines.extend(["> 状态：已被后续事件替代。保留原文供追溯。", ""])
            elif status == "retracted":
                lines.extend(["> 状态：已撤回。保留原文供追溯。", ""])
            lines.extend([event["summary"], "", "### 实录", ""])
            for fact in event["facts"]:
                evidence = "、".join(f"`{item}`" for item in fact["evidence_ids"])
                lines.append(f"- {fact['statement']}〔{evidence}〕")
            lines.extend(["", "### 可供文章取用", ""])
            if event["zhihu_angles"]:
                lines.extend(f"- {angle}" for angle in event["zhihu_angles"])
            else:
                lines.append("- 暂无已确认角度。")
            lines.extend(["", f"标签　{' · '.join(event['tags'])}", "", "### 史证", ""])
            lines.extend(_render_evidence(item) for item in event["evidence"])
            commentary = event.get("commentary")
            if commentary and not (
                manifest["visibility"] == "public"
                and commentary["visibility"] != "public"
            ):
                lines.extend(["", "### 太史公曰", "", commentary["text"]])
            if event["supersedes"]:
                lines.extend(["", "替代事件　" + "、".join(event["supersedes"])])
            if event["retracts"]:
                lines.extend(["", "撤回事件　" + "、".join(event["retracts"])])
            lines.extend(["", f"事件标识　`{event['event_id']}`", ""])

    chronicle_path = (seed_path / manifest["chronicle_file"]).resolve()
    if chronicle_path.parent != seed_path:
        raise ChronicleError("传记输出路径越出 seed")
    _write_text_atomic(chronicle_path, "\n".join(lines).rstrip() + "\n")
    return chronicle_path


def render_chronicle(seed_dir: Path | str, project_id: str) -> Path:
    seed_path = Path(seed_dir).resolve()
    project_dir = _project_dir(seed_path, project_id)
    with _project_lock(project_dir):
        manifest = _load_json(_manifest_path(seed_path, project_id))
        events = load_events(seed_path, project_id)
        return _render_chronicle_unlocked(seed_path, project_id, manifest, events)


def _iter_project_ids(seed_dir: Path | str) -> Iterator[str]:
    projects_dir = _store_root(seed_dir) / "projects"
    if not projects_dir.is_dir():
        return
    for child in sorted(projects_dir.iterdir()):
        if child.is_dir() and (child / "manifest.json").is_file():
            yield child.name


def search_events(
    seed_dir: Path | str,
    *,
    query: str = "",
    tags: list[str] | None = None,
    include_inactive: bool = False,
) -> list[dict[str, Any]]:
    wanted_tags = {tag.casefold() for tag in (tags or [])}
    query_folded = query.casefold().strip()
    matches: list[dict[str, Any]] = []
    for project_id in _iter_project_ids(seed_dir):
        events = load_events(seed_dir, project_id)
        statuses = _event_statuses(events)
        for event in events:
            if not include_inactive and statuses[event["event_id"]] != "active":
                continue
            event_tags = {str(tag).casefold() for tag in event["tags"]}
            if wanted_tags and not wanted_tags.issubset(event_tags):
                continue
            searchable_fields = {
                "title": event["title"],
                "summary": event["summary"],
                "facts": [fact["statement"] for fact in event["facts"]],
                "tags": event["tags"],
                "zhihu_angles": event["zhihu_angles"],
            }
            searchable = _json_text(searchable_fields).casefold()
            if query_folded and query_folded not in searchable:
                continue
            item = dict(event)
            item["status"] = statuses[event["event_id"]]
            matches.append(item)
    return sorted(matches, key=lambda item: (item["occurred_on"], item["event_id"]), reverse=True)


def validate_store(seed_dir: Path | str, project_id: str | None = None) -> list[str]:
    errors: list[str] = []
    project_ids = [project_id] if project_id else list(_iter_project_ids(seed_dir))
    if not project_ids:
        return ["史官仓库不存在或尚未注册任何项目"]
    for current_id in project_ids:
        try:
            seed_path = Path(seed_dir).resolve()
            manifest = _load_json(_manifest_path(seed_path, current_id))
            _validate_manifest(manifest, current_id, seed_path)
            events = load_events(seed_dir, current_id)
            state = _load_json(_project_dir(seed_path, current_id) / "state.json")
            _validate_state(state, current_id, events)
        except ChronicleError as error:
            errors.append(f"{current_id}: {error}")
            continue

        seen: set[str] = set()
        seen_evidence: dict[str, str] = {}
        transitioned: set[str] = set()
        for event in events:
            try:
                _validate_event(event, current_id)
            except ChronicleError as error:
                errors.append(f"{current_id}/{event.get('event_id', '?')}: {error}")
                continue
            event_id = event["event_id"]
            if event_id in seen:
                errors.append(f"{current_id}: event_id 重复：{event_id}")
            for relation in ("supersedes", "retracts"):
                unknown = set(event[relation]) - seen
                if unknown:
                    errors.append(
                        f"{current_id}/{event_id}: {relation} 引用未知或未来事件 "
                        + ", ".join(sorted(unknown))
                    )
                repeated = set(event[relation]) & transitioned
                if repeated:
                    errors.append(
                        f"{current_id}/{event_id}: 事件重复发生状态迁移 "
                        + ", ".join(sorted(repeated))
                    )
                transitioned.update(event[relation])
            commentary = event.get("commentary")
            if commentary:
                unknown = set(commentary["based_on"]) - (seen | {event_id})
                if unknown:
                    errors.append(
                        f"{current_id}/{event_id}: commentary.based_on 引用未知或未来事件 "
                        + ", ".join(sorted(unknown))
                    )
                if (
                    manifest["visibility"] == "public"
                    and commentary["visibility"] != "public"
                ):
                    errors.append(
                        f"{current_id}/{event_id}: 公开项目含 private commentary"
                    )
            if manifest["visibility"] == "public" and event["visibility"] != "public":
                errors.append(f"{current_id}/{event_id}: 公开项目含 private 事件")
            for evidence in event["evidence"]:
                owner = seen_evidence.get(evidence["id"])
                if owner:
                    errors.append(
                        f"{current_id}/{event_id}: evidence.id 已见于 {owner}: {evidence['id']}"
                    )
                else:
                    seen_evidence[evidence["id"]] = event_id
            seen.add(event_id)
    return errors


def _read_event(path_value: str) -> dict[str, Any]:
    try:
        if path_value == "-":
            value = _strict_json_loads(sys.stdin.read())
        else:
            value = _strict_json_loads(Path(path_value).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ChronicleError) as error:
        raise ChronicleError(f"无法读取事件 JSON：{error}") from error
    if not isinstance(value, dict):
        raise ChronicleError("事件文件必须包含一个 JSON 对象")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="维护可核验、可检索的项目传")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="注册项目并创建项目传")
    init_parser.add_argument("--seed", required=True)
    init_parser.add_argument("--project-id", required=True)
    init_parser.add_argument("--project-name", required=True)
    init_parser.add_argument("--remote", default="")
    init_parser.add_argument("--visibility", choices=sorted(VISIBILITIES), default="private")
    init_parser.add_argument("--summary", default="")

    append_parser = subparsers.add_parser("append", help="追加一条经过确认的事件")
    append_parser.add_argument("--seed", required=True)
    append_parser.add_argument("--project-id", required=True)
    append_parser.add_argument("--event", required=True, help="JSON 文件路径，或 - 从标准输入读取")
    append_parser.add_argument("--cursor")

    render_parser = subparsers.add_parser("render", help="从事件库重建项目传")
    render_parser.add_argument("--seed", required=True)
    render_parser.add_argument("--project-id", required=True)

    search_parser = subparsers.add_parser("search", help="检索可供写作的项目案例")
    search_parser.add_argument("--seed", required=True)
    search_parser.add_argument("--query", default="")
    search_parser.add_argument("--tag", action="append", default=[])
    search_parser.add_argument("--include-inactive", action="store_true")

    scan_parser = subparsers.add_parser("scan", help="列出游标之后的 Git 事件候选")
    scan_parser.add_argument("--seed", required=True)
    scan_parser.add_argument("--project-id", required=True)
    scan_parser.add_argument("--repo", required=True)
    scan_parser.add_argument("--branch", default="HEAD")

    validate_parser = subparsers.add_parser("validate", help="验证项目传数据")
    validate_parser.add_argument("--seed", required=True)
    validate_parser.add_argument("--project-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            path = init_project(
                args.seed,
                project_id=args.project_id,
                project_name=args.project_name,
                remote=args.remote,
                visibility=args.visibility,
                project_summary=args.summary,
            )
            print(path)
        elif args.command == "append":
            added = append_event(
                args.seed,
                args.project_id,
                _read_event(args.event),
                cursor=args.cursor,
            )
            print("ADDED" if added else "UNCHANGED")
        elif args.command == "render":
            print(render_chronicle(args.seed, args.project_id))
        elif args.command == "search":
            print(
                json.dumps(
                    search_events(
                        args.seed,
                        query=args.query,
                        tags=args.tag,
                        include_inactive=args.include_inactive,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "scan":
            print(
                json.dumps(
                    scan_git_commits(
                        args.seed,
                        args.project_id,
                        args.repo,
                        branch=args.branch,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.command == "validate":
            errors = validate_store(args.seed, args.project_id)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print("VALID")
    except ChronicleError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
