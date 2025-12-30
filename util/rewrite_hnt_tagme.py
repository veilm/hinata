#!/usr/bin/env python3
import argparse
import os
import re
import shlex
import subprocess
import sys


def run_git(args, cwd, capture=True, check=True):
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=capture,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            "git command failed: git {}\n{}\n{}".format(
                " ".join(args), result.stdout.strip(), result.stderr.strip()
            )
        )
    return result


def get_repo_root(repo):
    res = run_git(["rev-parse", "--show-toplevel"], repo)
    return res.stdout.strip()


def ensure_clean(repo):
    res = run_git(["status", "--porcelain"], repo)
    if res.stdout.strip():
        raise RuntimeError("working tree is dirty; commit or stash changes first")


def generate_message_from_diff(diff_text, max_len):
    compact = " ".join(diff_text.split())
    if not compact:
        return "chore: update"
    return compact[:max_len]


def rewrite_one(repo, regex, max_len):
    msg_res = run_git(["log", "-1", "--format=%B"], repo)
    message = msg_res.stdout.strip()
    if not re.search(regex, message):
        return 0

    diff_res = run_git(["show", "--format=", "--no-color", "HEAD"], repo)
    new_message = generate_message_from_diff(diff_res.stdout, max_len)

    author_date_res = run_git(["show", "-s", "--format=%aI", "HEAD"], repo)
    author_date = author_date_res.stdout.strip()

    env = os.environ.copy()
    env["GIT_COMMITTER_DATE"] = author_date

    amend = subprocess.run(
        ["git", "commit", "--amend", "-m", new_message],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )
    if amend.returncode != 0:
        raise RuntimeError(
            "git commit --amend failed:\n{}\n{}".format(
                amend.stdout.strip(), amend.stderr.strip()
            )
        )
    return 0


def rebase_rewrite(repo, regex, max_len, limit, allow_dirty, include_merges):
    repo_root = get_repo_root(repo)
    if not allow_dirty:
        ensure_clean(repo_root)

    count_res = run_git(["rev-list", "--count", "HEAD"], repo_root)
    total = int(count_res.stdout.strip() or "0")

    script_path = os.path.abspath(__file__)
    x_cmd = [
        "python3",
        script_path,
        "--rewrite-one",
        "--repo",
        repo_root,
        "--regex",
        regex,
        "--max-len",
        str(max_len),
    ]
    x_cmd_str = " ".join(shlex.quote(part) for part in x_cmd)

    rebase_args = ["rebase", "--committer-date-is-author-date", "-x", x_cmd_str]
    if include_merges:
        rebase_args.insert(1, "--rebase-merges")

    if total <= limit:
        rebase_args.append("--root")
    else:
        rebase_args.append("HEAD~{}".format(limit))

    run_git(rebase_args, repo_root, capture=False, check=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Rewrite matching commit messages in the last N commits."
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the git repo (default: current directory).",
    )
    parser.add_argument(
        "--regex",
        default=r"20[0-9][0-9] hnt-tagme$",
        help="Regex to match commit messages for rewriting.",
    )
    parser.add_argument(
        "--max-len",
        type=int,
        default=50,
        help="Max length for stub commit messages.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Number of most recent commits to scan/rewrite.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow running with a dirty working tree.",
    )
    parser.add_argument(
        "--no-merges",
        action="store_true",
        help="Do not preserve merges during rebase.",
    )
    parser.add_argument(
        "--rewrite-one",
        action="store_true",
        help="Internal: rewrite the current HEAD commit if it matches.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    repo_root = get_repo_root(args.repo)

    if args.rewrite_one:
        return rewrite_one(repo_root, args.regex, args.max_len)

    rebase_rewrite(
        repo_root,
        args.regex,
        args.max_len,
        args.limit,
        args.allow_dirty,
        include_merges=not args.no_merges,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("error: {}".format(exc), file=sys.stderr)
        sys.exit(1)
