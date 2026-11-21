#!/usr/bin/env python3
"""Negative and idempotence tests for the Zhihu ingestion gate.

Fixtures are synthetic. They must never be written into the live catalog.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

import zhihu_ingest as gate  # noqa: E402


BODY = "Fixture public note about a general method. It names no person and cites no private setting.\n"
DECK = "Fixture public note about a general method."
ANSWER_ID = "3000000000000000001"
QUESTION_ID = "3000000000000000002"
ANSWER_URL = f"https://www.zhihu.com/question/{QUESTION_ID}/answer/{ANSWER_ID}"
APPROVAL_ID = "approval-future-001"
PRIVATE_PATH = "/workspace/zhihu/not-on-this-vm/body.md"
LIVE_PATHS = (
    REPO / "content" / "article-catalog.json",
    REPO / "scripts" / "zhihu-sync" / "baseline.json",
    REPO / "scripts" / "zhihu-sync" / "ledger.json",
    REPO / "index.html",
    REPO / "script.js",
)
LIVE_BEFORE: dict[Path, bytes] = {}


def setUpModule() -> None:
    for path in LIVE_PATHS:
        LIVE_BEFORE[path] = path.read_bytes()


def tearDownModule() -> None:
    for path, content in LIVE_BEFORE.items():
        if path.read_bytes() != content:
            raise AssertionError(f"live site file changed during tests: {path}")


def merge(base: dict, override: dict) -> dict:
    for key, value in override.items():
        if value is DELETE:
            base.pop(key, None)
        elif isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


class Delete:
    pass


DELETE = Delete()


def manifest(**override: object) -> dict:
    document = {
        "schema_version": 1,
        "item": {
            "kind": "answer",
            "id": ANSWER_ID,
            "question_id": QUESTION_ID,
            "canonical_url": ANSWER_URL,
            "state": "published",
            "title": "Fixture public note",
            "body_markdown": BODY,
            "body_sha256": gate.sha256_text(BODY),
            "deck": DECK,
            "deck_provenance": "exact_excerpt",
        },
        "provenance": {
            "producer": "parent-routine",
            "collected_at": "2026-11-22T02:00:00+08:00",
            "published_at": "2026-11-22T01:00:00+08:00",
            "modified_at": "2026-11-22T01:00:00+08:00",
            "time_source": "exact_source_timestamp",
            "published_at_precision": "instant",
            "modified_at_precision": "instant",
            "collected_at_precision": "instant",
        },
        "baseline": {
            "baseline_id": gate.BASELINE_ID,
            "relation": "after_baseline",
        },
        "privacy_clearance": {
            "status": "cleared",
            "method": "separate_review",
            "cleared_by": "parent-routine",
            "cleared_at": "2026-11-22T02:10:00+08:00",
            "attestation": gate.PRIVACY_ATTESTATION,
            "hold_reasons": [],
            "argument_unchanged": True,
            "name_substitution_used": False,
            "regex_anonymizer_used": False,
        },
        "publish_approval": {
            "decision": "approve",
            "approval_id": APPROVAL_ID,
            "approved_by": "parent-routine",
            "approved_at": "2026-11-22T02:20:00+08:00",
        },
    }
    return merge(document, override)


class IngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        sync = self.root / "scripts" / "zhihu-sync"
        sync.mkdir(parents=True)
        shutil.copy(REPO / "scripts" / "zhihu-sync" / "baseline.json", sync / "baseline.json")
        shutil.copy(REPO / "scripts" / "zhihu-sync" / "ledger.json", sync / "ledger.json")
        content = self.root / "content"
        content.mkdir()
        catalog = {
            "sections": {
                "buzz": {"label": "炒作栏目", "anchor": "index.html#buzz", "context": "站内原文归档"}
            },
            "stages": [],
            "series": [],
            "articles": [
                {
                    "slug": "sample",
                    "content": "content/sample.md",
                    "section": "buzz",
                    "title": "Sample",
                    "deck": "Sample deck",
                    "format": "markdown",
                    "order": 0,
                }
            ],
        }
        (content / "article-catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (content / "sample.md").write_text("Sample\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def evaluate(self, document: dict) -> dict:
        return gate.evaluate_manifest(self.root, document)

    def ingest(self, document: dict, approve: str | None = APPROVAL_ID) -> dict:
        return gate.ingest_manifest(self.root, document, approve)

    def content_files(self) -> set[str]:
        return {path.name for path in (self.root / "content").glob("*.md")}

    def test_missing_body_is_held_and_unknown(self) -> None:
        result = self.evaluate(manifest(item={"body_markdown": None, "body_sha256": None}))
        self.assertEqual(result["decision"], "hold")
        self.assertIn("missing_body", result["reasons"])
        self.assertIn("item.body_markdown", result["unknown_fields"])
        self.assertEqual(result["identity"]["kind"], "answer")
        self.assertEqual(result["identity"]["id"], ANSWER_ID)
        self.assertFalse(result["wrote"])
        self.assertEqual(self.content_files(), {"sample.md"})
        self.assertNotIn(BODY, json.dumps(result))

    def test_duplicate_ingest_is_idempotent(self) -> None:
        first = self.ingest(manifest())
        second = self.ingest(manifest())
        catalog = json.loads((self.root / "content" / "article-catalog.json").read_text(encoding="utf-8"))
        slugs = [article["slug"] for article in catalog["articles"]]
        self.assertEqual(first["decision"], "publish")
        self.assertTrue(first["wrote"])
        self.assertEqual(second["decision"], "skip")
        self.assertIn("idempotent_duplicate", second["reasons"])
        self.assertFalse(second["wrote"])
        self.assertEqual(slugs.count(f"zhihu-answer-{ANSWER_ID}"), 1)

    def test_same_identity_with_a_different_body_is_not_replaced(self) -> None:
        self.ingest(manifest())
        target = self.root / "content" / f"zhihu-answer-{ANSWER_ID}.md"
        before = target.read_text(encoding="utf-8")
        changed = BODY.replace("general", "altered")
        result = self.ingest(
            manifest(item={"body_markdown": changed, "body_sha256": gate.sha256_text(changed), "deck": "Fixture public note about a altered method."})
        )
        self.assertEqual(result["decision"], "hold")
        self.assertIn("possible_edit_not_applied", result["reasons"])
        self.assertEqual(target.read_text(encoding="utf-8"), before)
        self.assertNotIn("某某", target.read_text(encoding="utf-8"))

    def test_historic_timestamp_is_held(self) -> None:
        result = self.ingest(
            manifest(
                provenance={
                    "published_at": "2026-11-21T23:00:00+08:00",
                    "modified_at": "2026-11-21T23:00:00+08:00",
                    "collected_at": "2026-11-21T23:30:00+08:00",
                },
                baseline={"relation": "historic"},
            )
        )
        self.assertEqual(result["decision"], "hold")
        self.assertIn("historic_before_baseline", result["reasons"])
        self.assertEqual(self.content_files(), {"sample.md"})

    def test_date_only_precision_stays_unknown(self) -> None:
        result = self.evaluate(
            manifest(
                provenance={
                    "time_source": "date_only",
                    "published_at": "2026-11-22",
                    "published_at_precision": "day",
                    "modified_at": "2026-11-22",
                    "modified_at_precision": "day",
                    "collected_at": None,
                    "collected_at_precision": "unknown",
                }
            )
        )
        self.assertEqual(result["decision"], "hold")
        self.assertIn("time_source_not_exact", result["reasons"])
        self.assertIn("provenance.published_at", result["unknown_fields"])
        self.assertIn("provenance.collected_at", result["unknown_fields"])
        self.assertNotIn("2026-11-22T00:00:00", json.dumps(result))

    def test_previously_held_answer_is_not_published(self) -> None:
        baseline = json.loads((self.root / "scripts" / "zhihu-sync" / "baseline.json").read_text(encoding="utf-8"))
        held = next(item for item in baseline["holds"] if item["hold_id"] == "zh-p02")
        result = self.ingest(
            manifest(
                item={
                    "id": held["id"],
                    "question_id": held["question_id"],
                    "canonical_url": held["canonical_url"],
                    "title": held["title"],
                }
            )
        )
        self.assertEqual(result["decision"], "hold")
        self.assertIn("explicit_confirmation_required", result["reasons"])
        self.assertFalse(result["wrote"])
        self.assertEqual(self.content_files(), {"sample.md"})
        self.assertNotIn("body_markdown", json.dumps(result))

    def test_unresolved_hold_matches_exact_title_only(self) -> None:
        baseline = json.loads((self.root / "scripts" / "zhihu-sync" / "baseline.json").read_text(encoding="utf-8"))
        held = next(item for item in baseline["holds"] if item["hold_id"] == "zh-p01")
        self.assertIsNone(held["id"])
        self.assertIsNone(held["canonical_url"])
        result = self.evaluate(manifest(item={"title": held["title"]}))
        self.assertEqual(result["decision"], "hold")
        self.assertIn("matches_unresolved_hold", result["reasons"])
        self.assertIn("explicit_confirmation_required", result["reasons"])

    def test_unreviewed_privacy_is_held(self) -> None:
        result = self.evaluate(manifest(privacy_clearance={"status": "unreviewed"}))
        self.assertEqual(result["decision"], "hold")
        self.assertIn("privacy_unreviewed", result["reasons"])
        self.assertEqual(self.content_files(), {"sample.md"})

    def test_name_substitution_is_not_applied_or_treated_as_clearance(self) -> None:
        original = "The fixture argument stays specific.\n"
        result = self.ingest(
            manifest(
                item={
                    "body_markdown": original,
                    "body_sha256": gate.sha256_text(original),
                    "deck": "The fixture argument stays specific.",
                },
                privacy_clearance={
                    "status": "cleared",
                    "method": "name_substitution",
                    "name_substitution_used": True,
                    "hold_reasons": [],
                },
            )
        )
        self.assertEqual(result["decision"], "hold")
        self.assertIn("privacy_clearance_rejected", result["reasons"])
        self.assertNotIn("某某", json.dumps(result, ensure_ascii=False))
        self.assertEqual(self.content_files(), {"sample.md"})
        self.assertNotIn("某某", (SCRIPTS / "zhihu_ingest.py").read_text(encoding="utf-8"))

    def test_regex_method_does_not_clear_privacy(self) -> None:
        result = self.evaluate(manifest(privacy_clearance={"method": "regex", "regex_anonymizer_used": True}))
        self.assertEqual(result["decision"], "hold")
        self.assertIn("privacy_clearance_rejected", result["reasons"])

    def test_ambiguous_clearance_with_hold_reasons_is_not_labeled_safe(self) -> None:
        result = self.evaluate(manifest(privacy_clearance={"status": "cleared", "hold_reasons": ["possible_named_person"]}))
        self.assertEqual(result["decision"], "hold")
        self.assertNotEqual(result["decision"], "eligible")
        self.assertIn("privacy_clearance_rejected", result["reasons"])

    def test_sha_mismatch_is_a_validation_failure(self) -> None:
        result = self.ingest(manifest(item={"body_sha256": "0" * 64}))
        self.assertEqual(result["decision"], "reject")
        self.assertIn("body_sha256_mismatch", result["reasons"])
        self.assertEqual(self.content_files(), {"sample.md"})

    def test_numeric_id_is_rejected(self) -> None:
        result = self.evaluate(manifest(item={"id": 3000000000000000001}))
        self.assertEqual(result["decision"], "reject")
        self.assertIn("identity_id_must_be_string", result["reasons"])

    def test_comment_and_draft_are_out_of_scope(self) -> None:
        comment = self.evaluate(manifest(item={"kind": "comment"}))
        draft = self.evaluate(manifest(item={"state": "draft"}))
        self.assertEqual(comment["decision"], "reject")
        self.assertIn("kind_out_of_scope", comment["reasons"])
        self.assertEqual(draft["decision"], "reject")
        self.assertIn("state_out_of_scope", draft["reasons"])

    def test_body_path_is_not_read_or_echoed(self) -> None:
        document = manifest()
        document["body_path"] = PRIVATE_PATH
        result = self.ingest(document)
        encoded = json.dumps(result)
        self.assertEqual(result["decision"], "reject")
        self.assertIn("body_path_not_accepted", result["reasons"])
        self.assertNotIn(PRIVATE_PATH, encoded)
        self.assertNotIn("not-on-this-vm", encoded)
        self.assertEqual(self.content_files(), {"sample.md"})

    def test_secret_material_is_rejected_without_echo(self) -> None:
        document = manifest()
        document["access_token"] = "ZHIHU_ACCESS_SECRET-example"
        result = self.evaluate(document)
        self.assertEqual(result["decision"], "reject")
        self.assertIn("secret_material", result["reasons"])
        self.assertNotIn("ZHIHU_ACCESS_SECRET", json.dumps(result))

    def test_site_boundary_text_is_held_not_rewritten(self) -> None:
        private_name = chr(0x9EC4) + chr(0x5357) + chr(0x6A35)
        body = f"Fixture mentions {private_name} and keeps the rest.\n"
        result = self.ingest(
            manifest(item={"body_markdown": body, "body_sha256": gate.sha256_text(body), "deck": "Fixture mentions"})
        )
        self.assertEqual(result["decision"], "hold")
        self.assertIn("site_privacy_boundary", result["reasons"])
        self.assertEqual(self.content_files(), {"sample.md"})

    def test_manifest_approval_without_cli_flag_does_not_write(self) -> None:
        eligible = self.evaluate(manifest())
        refused = self.ingest(manifest(), approve=None)
        mismatched = self.ingest(manifest(), approve="approval-other-001")
        self.assertEqual(eligible["decision"], "eligible")
        self.assertFalse(eligible["wrote"])
        self.assertEqual(refused["decision"], "hold")
        self.assertIn("cli_approval_required", refused["reasons"])
        self.assertEqual(mismatched["decision"], "hold")
        self.assertIn("approval_mismatch", mismatched["reasons"])
        self.assertEqual(self.content_files(), {"sample.md"})

    def test_explicit_approval_writes_a_buzz_entry_without_generated_js(self) -> None:
        result = self.ingest(manifest())
        slug = f"zhihu-answer-{ANSWER_ID}"
        catalog = json.loads((self.root / "content" / "article-catalog.json").read_text(encoding="utf-8"))
        article = next(item for item in catalog["articles"] if item["slug"] == slug)
        ledger = json.loads((self.root / "scripts" / "zhihu-sync" / "ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(result["decision"], "publish")
        self.assertEqual((self.root / "content" / f"{slug}.md").read_text(encoding="utf-8"), BODY)
        self.assertEqual(article["section"], "buzz")
        self.assertEqual(article["format"], "markdown")
        self.assertNotIn("stage", article)
        self.assertEqual(article["source"]["url"], ANSWER_URL)
        self.assertEqual(article["topic"], "知乎回答")
        self.assertEqual(article["kicker"], "知乎回答")
        self.assertEqual(article["deck"], DECK)
        self.assertEqual(article["date"], "发布于 2026-11-22")
        self.assertEqual(article["datePublished"], "2026-11-22")
        self.assertEqual(article["order"], -10)
        self.assertEqual(ledger["items"][0]["body_sha256"], gate.sha256_text(BODY))
        self.assertNotIn(BODY.strip(), json.dumps(ledger, ensure_ascii=False))
        self.assertFalse((self.root / "article-catalog.js").exists())
        self.assertFalse((self.root / "article-data.js").exists())
        self.assertEqual(result["unknown_fields"], [])

    def test_real_catalog_entries_stay_intact_when_a_fixture_is_added_in_temp(self) -> None:
        real = json.loads((REPO / "content" / "article-catalog.json").read_text(encoding="utf-8"))
        catalog_path = self.root / "content" / "article-catalog.json"
        catalog_path.write_text(json.dumps(real, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result = self.ingest(manifest())
        updated = json.loads(catalog_path.read_text(encoding="utf-8"))
        old_by_slug = {article["slug"]: article for article in real["articles"]}
        new_articles = [article for article in updated["articles"] if article["slug"] not in old_by_slug]
        self.assertEqual(result["decision"], "publish")
        self.assertEqual(len(new_articles), 1)
        for article in updated["articles"]:
            if article["slug"] in old_by_slug:
                self.assertEqual(article, old_by_slug[article["slug"]])
        buzz_slugs = [article["slug"] for article in updated["articles"] if article["section"] == "buzz"]
        self.assertEqual(buzz_slugs[-1], new_articles[0]["slug"])
        self.assertFalse((REPO / "content" / f"zhihu-answer-{ANSWER_ID}.md").exists())

    def test_hold_release_still_requires_a_full_manifest(self) -> None:
        baseline = json.loads((self.root / "scripts" / "zhihu-sync" / "baseline.json").read_text(encoding="utf-8"))
        held = next(item for item in baseline["holds"] if item["hold_id"] == "zh-p02")
        token = "confirm-zh-p02-0001"
        recorded = gate.release_hold(self.root, "zh-p02", token)
        self.assertEqual(recorded["decision"], "confirmation_recorded")
        self.assertFalse(recorded["publishes"])
        self.assertNotIn(token, json.dumps(recorded))
        document = manifest(
            item={
                "id": held["id"],
                "question_id": held["question_id"],
                "canonical_url": held["canonical_url"],
                "title": "Fixture confirmation",
            },
            provenance={
                "published_at": "2026-10-26T08:00:00+08:00",
                "modified_at": "2026-10-26T08:00:00+08:00",
                "collected_at": "2026-11-22T02:00:00+08:00",
            },
            baseline={"relation": "historic"},
            hold_release={"hold_id": "zh-p02", "confirm_token": token},
        )
        refused = gate.ingest_manifest(self.root, document, None)
        self.assertEqual(refused["decision"], "hold")
        published = gate.ingest_manifest(self.root, document, APPROVAL_ID)
        self.assertEqual(published["decision"], "publish")
        self.assertTrue(published["wrote"])
        updated = json.loads((self.root / "scripts" / "zhihu-sync" / "baseline.json").read_text(encoding="utf-8"))
        self.assertNotIn("zh-p02", [item["hold_id"] for item in updated["holds"]])

    def test_unresolved_hold_cannot_be_confirmed_before_identity_is_registered(self) -> None:
        early = gate.release_hold(self.root, "zh-p01", "confirm-zh-p01-0001")
        self.assertEqual(early["decision"], "hold")
        self.assertIn("canonical_identity_incomplete", early["reasons"])
        registered = gate.register_hold_identity(
            self.root,
            "zh-p01",
            "answer",
            "3000000000000000777",
            "3000000000000000888",
            "https://www.zhihu.com/question/3000000000000000888/answer/3000000000000000777",
        )
        self.assertEqual(registered["decision"], "identity_registered")
        self.assertIn("explicit_confirmation_required", registered["reasons"])
        baseline = json.loads((self.root / "scripts" / "zhihu-sync" / "baseline.json").read_text(encoding="utf-8"))
        hold = next(item for item in baseline["holds"] if item["hold_id"] == "zh-p01")
        self.assertEqual(hold["disposition"], "held_pending_confirmation")
        self.assertIsNone(hold["confirmation"])

    def test_collector_csv_cannot_publish_and_does_not_invent_times(self) -> None:
        csv_path = self.root / "works_latest.csv"
        csv_path.write_text(
            "title,type,date,upvotes,comments,favorites,url\n"
            "Fixture title,回答,2026-11-22,3,4,5,"
            f"{ANSWER_URL}\n"
            "Fixture comment,评论,2026-11-22,0,1,0,"
            f"{ANSWER_URL}\n",
            encoding="utf-8",
        )
        result = gate.inspect_csv(csv_path)
        self.assertEqual(result["decision"], "reject")
        answer, comment = result["rows"]
        self.assertEqual(answer["decision"], "hold")
        self.assertIsNone(answer["published_at"])
        self.assertIsNone(answer["modified_at"])
        self.assertIsNone(answer["collected_at"])
        self.assertEqual(answer["source_day"], "2026-11-22")
        self.assertIn("missing_body", answer["reasons"])
        self.assertIn("comments_not_ingested", answer["reasons"])
        self.assertIn("item.body_markdown", answer["unknown_fields"])
        self.assertEqual(answer["identity"]["id"], ANSWER_ID)
        self.assertEqual(comment["decision"], "reject")
        self.assertIn("kind_out_of_scope", comment["reasons"])
        self.assertEqual(self.content_files(), {"sample.md"})

    def test_csv_extra_column_is_not_a_body_channel(self) -> None:
        csv_path = self.root / "works_latest.csv"
        csv_path.write_text(
            "title,type,date,upvotes,comments,favorites,url,body\n"
            f"Fixture,回答,2026-11-22,1,1,1,{ANSWER_URL},{PRIVATE_PATH}\n",
            encoding="utf-8",
        )
        result = gate.inspect_csv(csv_path)
        self.assertEqual(result["decision"], "reject")
        self.assertIn("csv_schema", result["reasons"])
        self.assertNotIn(PRIVATE_PATH, json.dumps(result))

    def test_cli_evaluate_and_ingest(self) -> None:
        manifest_path = self.root / "item.json"
        manifest_path.write_text(json.dumps(manifest(), ensure_ascii=False), encoding="utf-8")
        evaluated = subprocess.run(
            [sys.executable, str(SCRIPTS / "zhihu_ingest.py"), "--root", str(self.root), "evaluate", "--manifest", str(manifest_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
        self.assertEqual(json.loads(evaluated.stdout)["decision"], "eligible")
        self.assertNotIn(BODY.strip(), evaluated.stdout)
        ingested = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "zhihu_ingest.py"),
                "--root",
                str(self.root),
                "ingest",
                "--manifest",
                str(manifest_path),
                "--approve",
                APPROVAL_ID,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(ingested.returncode, 0, ingested.stderr)
        self.assertEqual(json.loads(ingested.stdout)["decision"], "publish")
        self.assertFalse((self.root / "scripts" / "zhihu-sync" / ".ingest.lock").exists())

    def test_article_kind_publishes_without_a_question_id(self) -> None:
        article_id = "3000000000000000099"
        url = f"https://zhuanlan.zhihu.com/p/{article_id}"
        result = self.ingest(
            manifest(item={"kind": "article", "id": article_id, "question_id": None, "canonical_url": url})
        )
        self.assertEqual(result["decision"], "publish", result["reasons"])
        catalog = json.loads((self.root / "content" / "article-catalog.json").read_text(encoding="utf-8"))
        article = next(item for item in catalog["articles"] if item["slug"] == f"zhihu-article-{article_id}")
        self.assertEqual(article["section"], "buzz")
        self.assertEqual(article["topic"], "知乎文章")
        self.assertEqual(article["source"]["label"], "知乎原文")
        self.assertEqual(article["source"]["url"], url)
        self.assertNotIn("stage", article)

    def test_published_contract_mentions_the_exact_attestation(self) -> None:
        handbook = (REPO / "docs" / "zhihu-ingest.md").read_text(encoding="utf-8")
        schema = json.loads((REPO / "scripts" / "zhihu-sync" / "handoff.schema.json").read_text(encoding="utf-8"))
        self.assertIn(gate.PRIVACY_ATTESTATION, handbook)
        self.assertIn("separate_review", schema["properties"]["privacy_clearance"]["properties"]["method"]["enum"])
        self.assertIn("name_substitution", schema["properties"]["privacy_clearance"]["properties"]["method"]["enum"])
        self.assertNotIn("regex guarantees", schema["description"].lower())

    def test_tooling_does_not_fetch_or_anonymize(self) -> None:
        source = (SCRIPTS / "zhihu_ingest.py").read_text(encoding="utf-8")
        self.assertNotIn("urllib", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("某某", source)

    def test_committed_baseline_matches_the_live_catalog(self) -> None:
        baseline = json.loads((REPO / "scripts" / "zhihu-sync" / "baseline.json").read_text(encoding="utf-8"))
        catalog = json.loads((REPO / "content" / "article-catalog.json").read_text(encoding="utf-8"))
        catalog_urls = {
            article["source"]["url"]
            for article in catalog["articles"]
            if isinstance(article.get("source"), dict) and "zhihu.com" in article["source"].get("url", "")
        }
        known_urls = {item["canonical_url"] for item in baseline["known"]}
        hold_urls = {item["canonical_url"] for item in baseline["holds"] if item.get("canonical_url")}
        self.assertEqual(known_urls, catalog_urls)
        self.assertEqual(len(baseline["holds"]), 3)
        self.assertTrue(hold_urls.isdisjoint(catalog_urls))
        self.assertEqual(baseline["sealed_at"], "2026-11-22T00:00:00+08:00")
        self.assertNotIn("body_markdown", json.dumps(baseline))
        unresolved = next(item for item in baseline["holds"] if item["hold_id"] == "zh-p01")
        self.assertIsNone(unresolved["id"])
        self.assertIsNone(unresolved["canonical_url"])
        ledger = json.loads((REPO / "scripts" / "zhihu-sync" / "ledger.json").read_text(encoding="utf-8"))
        self.assertEqual(ledger["items"], [])


if __name__ == "__main__":
    unittest.main()
