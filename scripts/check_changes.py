import argparse
import pathlib
import re
import subprocess
import sys

SUBJECT = re.compile(
    r"^(feat|fix|refactor|perf|test|docs|chore|build|ci|revert)\([a-z0-9][a-z0-9-]*\): \S.*$"
)
VAGUE_RESULTS = {"update", "updates", "fix", "fix bugs", "修复问题", "继续推进", "更新"}


def git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments], capture_output=True, text=True, encoding="utf-8", check=False
    )


def valid_subject(subject: str) -> bool:
    return (
        bool(SUBJECT.fullmatch(subject))
        and subject.split(": ", 1)[1].strip().lower() not in VAGUE_RESULTS
    )


def protected_group(path: str) -> str | None:
    parts = pathlib.PurePosixPath(path).parts
    if parts and parts[0] == "vendor":
        return "vendor"
    if "node_modules" in parts or ".next" in parts:
        return "dependency-output"
    if path in {"apps/web/next-env.d.ts", "apps/web/src/lib/api-schema.d.ts"}:
        return "generated"
    return None


def check_diff(arguments: list[str], subject: str | None = None) -> bool:
    whitespace = git("diff", "--check", *arguments)
    names = git("diff", "--name-only", "-z", *arguments)
    if whitespace.returncode or names.returncode:
        print(whitespace.stdout + whitespace.stderr + names.stderr)
        return False
    paths = [path for path in names.stdout.split("\0") if path]
    protected = {path: protected_group(path) for path in paths if protected_group(path)}
    if protected and subject is not None:
        groups = set(protected.values())
        group = next(iter(groups)) if len(groups) == 1 else None
        dedicated = group in {"vendor", "generated"} and subject.startswith(
            (f"chore({group}): ", f"build({group}): ")
        )
        if not dedicated or len(protected) != len(paths):
            print(
                "Protected paths need an isolated vendor/generated commit with an explicit scope."
            )
            print("\n".join(protected))
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--commit-msg", type=pathlib.Path)
    mode.add_argument("--range", dest="revision_range")
    mode.add_argument("--worktree", action="store_true")
    args = parser.parse_args()
    if args.commit_msg:
        lines = args.commit_msg.read_text(encoding="utf-8-sig").splitlines()
        subject = lines[0] if lines else ""
        if not valid_subject(subject):
            print("Commit blocked: use <type>(<scope>): <specific result>.")
            return 1
        return 0 if check_diff(["--cached"], subject) else 1
    if args.revision_range:
        commits = git("rev-list", "--no-merges", "--reverse", args.revision_range)
        if commits.returncode:
            print(commits.stderr)
            return 1
        valid = True
        for commit in commits.stdout.splitlines():
            message = git("show", "-s", "--format=%s", commit)
            subject = message.stdout.strip()
            if message.returncode or not valid_subject(subject):
                print(f"Invalid commit subject: {commit[:12]} {subject}")
                valid = False
            parent = git("rev-parse", f"{commit}^")
            base = (
                parent.stdout.strip()
                if parent.returncode == 0
                else "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
            )
            valid = check_diff([base, commit], subject) and valid
        return 0 if valid else 1
    return 0 if check_diff(["HEAD"] if args.worktree else ["--cached"]) else 1


if __name__ == "__main__":
    sys.exit(main())
