import argparse
import pathlib
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    scanner = shutil.which("gitleaks")
    if scanner is None:
        print("Commit blocked: install Gitleaks 8.30.1 and make it available on PATH.")
        return 1
    command = (
        ["git", "ls-files", "-z"]
        if args.history
        else ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    )
    result = subprocess.run(command, capture_output=True, check=True)
    for raw_path in result.stdout.split(b"\0"):
        name = pathlib.PurePosixPath(raw_path.decode("utf-8", errors="replace")).name
        if (name == ".env" or name.startswith(".env.")) and name != ".env.example":
            print("Commit blocked: a real environment file is staged/tracked. Unstage it.")
            return 1
    flags = ["--log-opts=--all"] if args.history else ["--pre-commit", "--staged"]
    return subprocess.run(
        [
            scanner,
            "git",
            "--config=.gitleaks.toml",
            "--redact=100",
            "--no-banner",
            "--ignore-gitleaks-allow",
            *flags,
            ".",
        ],
        check=False,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
