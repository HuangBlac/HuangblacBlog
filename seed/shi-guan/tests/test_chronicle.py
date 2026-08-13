from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from chronicle import (  # noqa: E402
    ChronicleError,
    append_event,
    init_project,
    load_events,
    render_chronicle,
    scan_git_commits,
    search_events,
    validate_store,
)

COMMIT_A = "a" * 40
COMMIT_B = "b" * 40
COMMIT_C = "c" * 40


def sample_event(event_id: str = "demo-20260812-line-endings") -> dict:
    return {
        "schema_version": 1,
        "event_id": event_id,
        "project_id": "demo",
        "occurred_on": "2026-08-12",
        "title": "统一跨平台换行处理",
        "summary": "项目统一了 Windows 与 Linux 的文章数据生成结果。",
        "facts": [
            {
                "statement": "同步脚本会先规范化换行，再生成文章数据。",
                "evidence_ids": [f"git:{COMMIT_A}"],
            }
        ],
        "evidence": [
            {
                "id": f"git:{COMMIT_A}",
                "type": "git_commit",
                "ref": COMMIT_A,
                "label": "fix(ci): normalize line endings",
            }
        ],
        "tags": ["CI", "PowerShell", "跨平台"],
        "visibility": "public",
        "zhihu_angles": ["同一份生成器怎样在 Windows 与 Linux 上保持一致"],
        "commentary": {
            "label": "太史公曰",
            "text": "小站之患，常不在大架构，先伏于一处换行。能把偶然失败改成固定检查，方可久行。",
            "based_on": [event_id],
            "visibility": "public",
        },
        "supersedes": [],
        "retracts": [],
    }


class ChronicleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.seed_dir = Path(self.temp_dir.name) / "seed"
        init_project(
            self.seed_dir,
            project_id="demo",
            project_name="Demo",
            remote="https://github.com/example/demo.git",
            visibility="private",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_init_creates_registry_state_and_chronicle(self) -> None:
        project_dir = self.seed_dir / ".shi-guan" / "projects" / "demo"
        self.assertTrue((project_dir / "manifest.json").is_file())
        self.assertTrue((project_dir / "state.json").is_file())
        self.assertTrue((project_dir / "events.jsonl").is_file())
        chronicle = self.seed_dir / "Demo传.md"
        self.assertTrue(chronicle.is_file())
        self.assertIn("尚无正式事件", chronicle.read_text(encoding="utf-8"))

    def test_append_is_idempotent_and_advances_cursor(self) -> None:
        event = sample_event()
        self.assertTrue(
            append_event(self.seed_dir, "demo", event, cursor=COMMIT_A)
        )
        self.assertFalse(
            append_event(self.seed_dir, "demo", event, cursor=COMMIT_A)
        )
        self.assertEqual(1, len(load_events(self.seed_dir, "demo")))

        state_path = (
            self.seed_dir / ".shi-guan" / "projects" / "demo" / "state.json"
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(COMMIT_A, state["last_commit"])

        chronicle = render_chronicle(self.seed_dir, "demo")
        rendered = chronicle.read_text(encoding="utf-8")
        self.assertEqual(1, rendered.count("统一跨平台换行处理"))
        self.assertIn("### 太史公曰", rendered)
        self.assertIn(f"git:{COMMIT_A}", rendered)

    def test_idempotent_retry_repairs_missing_render(self) -> None:
        event = sample_event()
        append_event(self.seed_dir, "demo", event, cursor=COMMIT_A)
        chronicle = self.seed_dir / "Demo传.md"
        chronicle.unlink()

        self.assertFalse(
            append_event(self.seed_dir, "demo", event, cursor=COMMIT_A)
        )
        self.assertTrue(chronicle.is_file())
        self.assertIn(event["title"], chronicle.read_text(encoding="utf-8"))

    def test_idempotent_retry_recovers_cursor_after_partial_commit(self) -> None:
        event = sample_event("demo-cursor-recovery")
        append_event(self.seed_dir, "demo", event, cursor=COMMIT_A)
        state_path = self.seed_dir / ".shi-guan" / "projects" / "demo" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["last_commit"] = None
        state["last_event_id"] = None
        state_path.write_text(json.dumps(state), encoding="utf-8")

        self.assertFalse(append_event(self.seed_dir, "demo", event, cursor=COMMIT_A))
        recovered = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(COMMIT_A, recovered["last_commit"])
        self.assertEqual(event["event_id"], recovered["last_event_id"])

    def test_idempotent_retry_recovers_cursor_after_later_partial_commit(self) -> None:
        first = sample_event("demo-first-committed")
        append_event(self.seed_dir, "demo", first, cursor=COMMIT_A)
        second = sample_event("demo-second-partial")
        second["evidence"][0].update({"id": f"git:{COMMIT_B}", "ref": COMMIT_B})
        second["facts"][0]["evidence_ids"] = [f"git:{COMMIT_B}"]
        append_event(self.seed_dir, "demo", second, cursor=COMMIT_B)
        state_path = self.seed_dir / ".shi-guan" / "projects" / "demo" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["last_commit"] = COMMIT_A
        state["last_event_id"] = first["event_id"]
        state_path.write_text(json.dumps(state), encoding="utf-8")

        self.assertFalse(append_event(self.seed_dir, "demo", second, cursor=COMMIT_B))
        recovered = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual(COMMIT_B, recovered["last_commit"])
        self.assertEqual(second["event_id"], recovered["last_event_id"])

    def test_old_event_retry_cannot_recover_cursor(self) -> None:
        first = sample_event("demo-old-recovery")
        append_event(self.seed_dir, "demo", first, cursor=COMMIT_A)
        second = sample_event("demo-new-recovery")
        second["evidence"][0].update({"id": f"git:{COMMIT_B}", "ref": COMMIT_B})
        second["facts"][0]["evidence_ids"] = [f"git:{COMMIT_B}"]
        append_event(self.seed_dir, "demo", second, cursor=COMMIT_B)
        state_path = self.seed_dir / ".shi-guan" / "projects" / "demo" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["last_commit"] = None
        state["last_event_id"] = None
        state_path.write_text(json.dumps(state), encoding="utf-8")

        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", first, cursor=COMMIT_A)

    def test_replaying_old_event_does_not_move_state_backwards(self) -> None:
        first = sample_event("demo-first")
        append_event(self.seed_dir, "demo", first, cursor=COMMIT_A)
        second = sample_event("demo-second")
        second["evidence"][0].update({"id": f"git:{COMMIT_B}", "ref": COMMIT_B})
        second["facts"][0]["evidence_ids"] = [f"git:{COMMIT_B}"]
        append_event(self.seed_dir, "demo", second, cursor=COMMIT_B)

        self.assertFalse(append_event(self.seed_dir, "demo", first, cursor=COMMIT_A))
        state_path = self.seed_dir / ".shi-guan" / "projects" / "demo" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual("demo-second", state["last_event_id"])
        self.assertEqual(COMMIT_B, state["last_commit"])

    def test_cursor_must_be_git_evidence_from_the_event(self) -> None:
        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", sample_event(), cursor=COMMIT_B)
        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", sample_event(), cursor="abc1234")

    def test_event_without_cursor_keeps_existing_scan_cursor_valid(self) -> None:
        append_event(self.seed_dir, "demo", sample_event("demo-git"), cursor=COMMIT_A)
        observation = sample_event("demo-user-statement")
        observation["evidence"] = [
            {
                "id": "user:confirmed-milestone",
                "type": "user_statement",
                "ref": "confirmed-in-current-task",
                "label": "用户确认阶段完成",
            }
        ]
        observation["facts"][0]["evidence_ids"] = ["user:confirmed-milestone"]
        append_event(self.seed_dir, "demo", observation)

        state_path = self.seed_dir / ".shi-guan" / "projects" / "demo" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual("demo-git", state["last_event_id"])
        self.assertEqual(COMMIT_A, state["last_commit"])
        self.assertEqual([], validate_store(self.seed_dir, "demo"))

    def test_same_day_events_keep_append_order_in_chronicle(self) -> None:
        first = sample_event("demo-z-first")
        append_event(self.seed_dir, "demo", first)
        second = sample_event("demo-a-second")
        second["title"] = "同日发生的第二件事"
        second["evidence"][0].update({"id": f"git:{COMMIT_B}", "ref": COMMIT_B})
        second["facts"][0]["evidence_ids"] = [f"git:{COMMIT_B}"]
        append_event(self.seed_dir, "demo", second)

        rendered = render_chronicle(self.seed_dir, "demo").read_text(encoding="utf-8")
        self.assertLess(rendered.index(first["title"]), rendered.index(second["title"]))

    def test_search_returns_fact_pack_by_query_and_tag(self) -> None:
        append_event(self.seed_dir, "demo", sample_event())
        by_query = search_events(self.seed_dir, query="Windows")
        by_tag = search_events(self.seed_dir, tags=["跨平台"])
        self.assertEqual("demo-20260812-line-endings", by_query[0]["event_id"])
        self.assertEqual("demo-20260812-line-endings", by_tag[0]["event_id"])

    def test_rejects_reusing_git_evidence_under_a_new_event_id(self) -> None:
        append_event(self.seed_dir, "demo", sample_event())
        duplicate = sample_event("demo-duplicate")
        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", duplicate)

    def test_rejects_short_or_mismatched_git_evidence(self) -> None:
        short = sample_event("demo-short-sha")
        short["evidence"][0].update({"id": "git:abc1234", "ref": "abc1234"})
        short["facts"][0]["evidence_ids"] = ["git:abc1234"]
        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", short)

        mismatch = sample_event("demo-mismatch-sha")
        mismatch["evidence"][0]["id"] = f"git:{COMMIT_B}"
        mismatch["facts"][0]["evidence_ids"] = [f"git:{COMMIT_B}"]
        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", mismatch)

    def test_commentary_references_existing_events_and_respects_visibility(self) -> None:
        missing_reference = sample_event("demo-missing-reference")
        missing_reference["commentary"]["based_on"] = ["does-not-exist"]
        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", missing_reference)

        too_public = sample_event("demo-too-public-commentary")
        too_public["visibility"] = "private"
        too_public["commentary"]["visibility"] = "public"
        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", too_public)

    def test_search_does_not_match_evidence_or_commentary_only(self) -> None:
        event = sample_event()
        event["commentary"]["text"] = "只在评论层出现的玄武门"
        event["evidence"][0]["label"] = "只在证据层出现的贞观"
        append_event(self.seed_dir, "demo", event)
        self.assertEqual([], search_events(self.seed_dir, query="玄武门"))
        self.assertEqual([], search_events(self.seed_dir, query="贞观"))

    def test_scan_lists_unseen_commits_without_advancing_cursor(self) -> None:
        repository = Path(self.temp_dir.name) / "repository"
        repository.mkdir()
        self._git(repository, "init")
        self._git(repository, "config", "user.name", "Test User")
        self._git(repository, "config", "user.email", "test@example.com")
        self._git(
            repository,
            "remote",
            "add",
            "origin",
            "https://github.com/example/demo.git",
        )
        (repository / "one.txt").write_text("one", encoding="utf-8")
        self._git(repository, "add", "one.txt")
        self._git(repository, "commit", "-m", "feat: first event")

        candidates = scan_git_commits(self.seed_dir, "demo", repository)
        self.assertEqual(1, len(candidates))
        self.assertEqual("feat: first event", candidates[0]["subject"])

        state_path = (
            self.seed_dir / ".shi-guan" / "projects" / "demo" / "state.json"
        )
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertIsNone(state["last_commit"])

        commit = candidates[0]["commit"]
        event = sample_event("demo-first-event")
        event["evidence"][0]["id"] = f"git:{commit}"
        event["evidence"][0]["ref"] = commit
        event["facts"][0]["evidence_ids"] = [f"git:{commit}"]
        append_event(self.seed_dir, "demo", event, cursor=commit)
        self.assertEqual([], scan_git_commits(self.seed_dir, "demo", repository))

        with self.assertRaises(ChronicleError):
            scan_git_commits(self.seed_dir, "demo", repository, branch="--all")

    def test_rejects_local_absolute_paths_in_event_material(self) -> None:
        paths = [
            "Z:" + "\\private-note.txt",
            "\\" * 2 + "server\\share\\private-note.txt",
            "/" + "tmp/private-note.txt",
            "file:" + "///var/private-note.txt",
        ]
        for index, private_path in enumerate(paths):
            event = sample_event(f"demo-20260812-private-path-{index}")
            event["facts"][0]["statement"] = f"文件位于 {private_path}"
            with self.assertRaises(ChronicleError):
                append_event(self.seed_dir, "demo", event)

    def test_rejects_insecure_public_evidence_url(self) -> None:
        event = sample_event("demo-insecure-url")
        event["evidence"] = [
            {
                "id": "url:example",
                "type": "public_url",
                "ref": "http://example.com/proof",
                "label": "公开证据",
            }
        ]
        event["facts"][0]["evidence_ids"] = ["url:example"]
        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", event)

    def test_rejects_duplicate_commentary_references(self) -> None:
        event = sample_event("demo-duplicate-commentary-reference")
        event["commentary"]["based_on"] = [event["event_id"], event["event_id"]]
        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", event)

    def test_rejects_strictly_invalid_dates(self) -> None:
        for invalid_date in ("20260812", "2026-W33-3"):
            event = sample_event(f"demo-date-{invalid_date.casefold().replace('-', '_')}")
            event["occurred_on"] = invalid_date
            with self.assertRaises(ChronicleError):
                append_event(self.seed_dir, "demo", event)

    def test_validate_rejects_damaged_manifest_and_state(self) -> None:
        append_event(self.seed_dir, "demo", sample_event(), cursor=COMMIT_A)
        project_dir = self.seed_dir / ".shi-guan" / "projects" / "demo"
        manifest_path = project_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["chronicle_file"] = "../victim.md"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertTrue(validate_store(self.seed_dir, "demo"))

        manifest["chronicle_file"] = "Demo传.md"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        state_path = project_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["last_commit"] = "HEAD"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        self.assertTrue(validate_store(self.seed_dir, "demo"))

    def test_validate_rejects_missing_store(self) -> None:
        self.assertTrue(validate_store(Path(self.temp_dir.name) / "missing-seed"))

    def test_public_project_rejects_private_commentary(self) -> None:
        public_seed = Path(self.temp_dir.name) / "public-seed"
        init_project(
            public_seed,
            project_id="public-demo",
            project_name="PublicDemo",
            remote="https://github.com/example/public-demo.git",
            visibility="public",
        )
        event = sample_event("public-commentary")
        event["project_id"] = "public-demo"
        event["commentary"]["based_on"] = [event["event_id"]]
        event["commentary"]["visibility"] = "private"
        with self.assertRaises(ChronicleError):
            append_event(public_seed, "public-demo", event)

    def test_rejects_cross_project_chronicle_filename_collision(self) -> None:
        with self.assertRaises(ChronicleError):
            init_project(
                self.seed_dir,
                project_id="demo-two",
                project_name="demo",
                remote="https://github.com/example/demo-two.git",
                visibility="private",
            )

    def test_superseded_and_retracted_events_are_marked(self) -> None:
        append_event(self.seed_dir, "demo", sample_event("demo-old"))
        replacement = sample_event("demo-new")
        replacement["evidence"][0].update(
            {"id": f"git:{COMMIT_B}", "ref": COMMIT_B, "label": "replacement"}
        )
        replacement["facts"][0]["evidence_ids"] = [f"git:{COMMIT_B}"]
        replacement["supersedes"] = ["demo-old"]
        append_event(self.seed_dir, "demo", replacement)
        withdrawal = sample_event("demo-withdrawal")
        withdrawal["evidence"][0].update(
            {"id": f"git:{COMMIT_C}", "ref": COMMIT_C, "label": "withdrawal"}
        )
        withdrawal["facts"][0]["evidence_ids"] = [f"git:{COMMIT_C}"]
        withdrawal["retracts"] = ["demo-new"]
        append_event(self.seed_dir, "demo", withdrawal)

        rendered = render_chronicle(self.seed_dir, "demo").read_text(encoding="utf-8")
        self.assertIn("状态：已被后续事件替代", rendered)
        self.assertIn("状态：已撤回", rendered)

    def test_rejects_conflicting_status_transitions(self) -> None:
        append_event(self.seed_dir, "demo", sample_event("demo-old"))
        invalid = sample_event("demo-invalid-transition")
        invalid["evidence"][0].update({"id": f"git:{COMMIT_B}", "ref": COMMIT_B})
        invalid["facts"][0]["evidence_ids"] = [f"git:{COMMIT_B}"]
        invalid["supersedes"] = ["demo-old"]
        invalid["retracts"] = ["demo-old"]
        with self.assertRaises(ChronicleError):
            append_event(self.seed_dir, "demo", invalid)

    def test_validate_store_detects_no_errors_for_valid_data(self) -> None:
        append_event(self.seed_dir, "demo", sample_event())
        self.assertEqual([], validate_store(self.seed_dir, "demo"))

    def test_validate_store_detects_duplicate_evidence_in_edited_jsonl(self) -> None:
        append_event(self.seed_dir, "demo", sample_event())
        duplicate = sample_event("demo-manual-duplicate")
        events_path = (
            self.seed_dir / ".shi-guan" / "projects" / "demo" / "events.jsonl"
        )
        with events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(duplicate, ensure_ascii=False) + "\n")
        errors = validate_store(self.seed_dir, "demo")
        self.assertTrue(any("evidence.id 已见于" in error for error in errors))

    def _git(self, repository: Path, *args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=repository,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return result.stdout.strip()


if __name__ == "__main__":
    unittest.main()
