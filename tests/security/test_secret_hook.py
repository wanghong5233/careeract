import pathlib
import shutil
import subprocess
import tempfile
import unittest
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("gitleaks") and shutil.which("uv"), "requires gitleaks and uv")
class SecretHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = pathlib.Path(self.temporary.name)
        for relative in (
            "scripts/check_secrets.py",
            "scripts/check_changes.py",
            ".githooks/pre-commit",
            ".gitleaks.toml",
        ):
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.git("init")
        self.git("config", "user.name", "Hook Test")
        self.git("config", "user.email", "hook@example.invalid")
        self.git("config", "core.hooksPath", ".githooks")
        (self.repo / ".githooks/pre-commit").chmod(0o755)

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments], cwd=self.repo, capture_output=True, text=True, check=False
        )

    def commit(self) -> subprocess.CompletedProcess[str]:
        return self.git(
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            "test(security): verify staged secret checks",
        )

    def test_clean_example_can_commit(self) -> None:
        (self.repo / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")
        self.assertEqual(self.git("add", ".env.example").returncode, 0)
        self.assertEqual(self.commit().returncode, 0)

    def test_environment_file_is_blocked_even_without_secret(self) -> None:
        (self.repo / ".env.local").write_text("MODE=test\n", encoding="utf-8")
        self.assertEqual(self.git("add", "-f", ".env.local").returncode, 0)
        self.assertNotEqual(self.commit().returncode, 0)
        self.assertNotEqual(self.git("rev-parse", "--verify", "HEAD").returncode, 0)

    def test_staged_secret_is_blocked_despite_clean_worktree(self) -> None:
        fake_secret = uuid.uuid4().hex + uuid.uuid4().hex
        probe = self.repo / "probe.txt"
        probe.write_text(f'api_key = "{fake_secret}"\n', encoding="utf-8")
        self.assertEqual(self.git("add", "probe.txt").returncode, 0)
        probe.write_text("clean worktree\n", encoding="utf-8")
        result = self.commit()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(fake_secret, result.stdout + result.stderr)
        self.assertNotEqual(self.git("rev-parse", "--verify", "HEAD").returncode, 0)

    def test_worktree_scan_includes_untracked_files_and_redacts_findings(self) -> None:
        fake_secret = uuid.uuid4().hex + uuid.uuid4().hex
        probe = self.repo / "probe.txt"
        probe.write_text(f'api_key = "{fake_secret}"\n', encoding="utf-8")
        self.git("add", ".")
        probe.write_text("clean\n", encoding="utf-8")
        self.git("add", "probe.txt")
        self.assertEqual(self.commit().returncode, 0)
        (self.repo / "untracked.txt").write_text(f'api_key = "{fake_secret}"\n', encoding="utf-8")
        result = subprocess.run(
            ["uv", "run", "--no-sync", "python", "scripts/check_secrets.py", "--worktree"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn(fake_secret, result.stdout + result.stderr)
        (self.repo / "untracked.txt").write_text("clean\n", encoding="utf-8")
        clean = subprocess.run(
            ["uv", "run", "--no-sync", "python", "scripts/check_secrets.py", "--worktree"],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
