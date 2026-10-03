import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class ChangeCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = pathlib.Path(self.temporary.name)
        for relative in ("scripts/check_changes.py", ".githooks/commit-msg"):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.git("init")
        self.git("config", "user.name", "Hook Test")
        self.git("config", "user.email", "hook@example.invalid")
        self.git("config", "core.hooksPath", ".githooks")
        (self.repo / ".githooks/commit-msg").chmod(0o755)

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments], cwd=self.repo, capture_output=True, text=True, check=False
        )

    def stage(self, path: str, content: str = "clean\n") -> None:
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.assertEqual(self.git("add", path).returncode, 0)

    def commit(self, subject: str) -> subprocess.CompletedProcess[str]:
        return self.git("-c", "commit.gpgsign=false", "commit", "-m", subject)

    def test_subject_format_and_specific_result(self) -> None:
        message = self.repo / "message.txt"
        for subject in ("fix(web): preserve drafts", "docs(workspace): record ownership rules"):
            message.write_text(subject, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "scripts/check_changes.py", "--commit-msg", str(message)],
                cwd=self.repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for subject in (
            "update",
            "fix: repair",
            "fix(web): update",
            "design(web): redesign",
            "fix(web): 修复问题",
            "fix(web): ",
        ):
            message.write_text(subject, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "scripts/check_changes.py", "--commit-msg", str(message)],
                cwd=self.repo,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_hook_blocks_bad_subject_and_accepts_scoped_commit(self) -> None:
        self.stage("source.py")
        self.assertNotEqual(self.commit("continue work").returncode, 0)
        self.assertEqual(self.commit("fix(api): preserve ownership checks").returncode, 0)

    def test_hook_blocks_staged_whitespace_despite_clean_worktree(self) -> None:
        self.stage("source.py", "trailing  \n")
        (self.repo / "source.py").write_text("clean\n", encoding="utf-8")
        self.assertNotEqual(self.commit("fix(api): preserve ownership checks").returncode, 0)

    def test_vendor_changes_need_isolated_explicit_scope(self) -> None:
        self.stage("vendor/library/file.py")
        self.assertNotEqual(self.commit("fix(web): repair navigation").returncode, 0)
        self.assertEqual(self.commit("chore(vendor): apply verified upstream fix").returncode, 0)
        self.stage("vendor/library/file.py", "changed\n")
        self.stage("source.py")
        self.assertNotEqual(self.commit("chore(vendor): apply verified upstream fix").returncode, 0)

    def test_dependency_output_cannot_be_committed(self) -> None:
        self.stage("apps/web/.next/cache/output.json")
        self.assertNotEqual(self.commit("chore(generated): refresh output").returncode, 0)

    def test_ci_range_uses_same_rules(self) -> None:
        self.stage("source.py")
        self.assertEqual(self.commit("fix(api): preserve ownership checks").returncode, 0)
        initial = self.git("rev-parse", "HEAD").stdout.strip()
        self.stage("source.py", "changed\n")
        self.assertEqual(self.commit("test(api): cover ownership checks").returncode, 0)
        result = subprocess.run(
            [sys.executable, "scripts/check_changes.py", "--range", f"{initial}..HEAD"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
