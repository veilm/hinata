#!/usr/bin/env python3
import argparse
import os
import re
import shlex
import subprocess
import sys


LLM_MODEL_STRING = "openrouter/google/gemini-3-flash-preview"
PROMPT_TEMPLATE_NAME = "commit_message_prompt.md"
DEFAULT_LLM_TIMEOUT = 60


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


def load_prompt_template():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, PROMPT_TEMPLATE_NAME)
    with open(template_path, "r", encoding="utf-8") as handle:
        return handle.read()


def render_prompt(diff_text):
    template = load_prompt_template()
    if "__COMMIT_DIFF__" not in template:
        raise RuntimeError("prompt template missing __COMMIT_DIFF__ placeholder")
    return template.replace("__COMMIT_DIFF__", diff_text)


def run_hnt_chat(prompt_text, timeout_seconds):
    chat_res = subprocess.run(
        ["hnt-chat", "new"],
        capture_output=True,
        text=True,
    )
    if chat_res.returncode != 0:
        raise RuntimeError(
            "hnt-chat new failed:\n{}\n{}".format(
                chat_res.stdout.strip(), chat_res.stderr.strip()
            )
        )
    chat_id = chat_res.stdout.strip()

    add_res = subprocess.run(
        ["hnt-chat", "add", "user", "-c", chat_id],
        input=prompt_text,
        text=True,
    )
    if add_res.returncode != 0:
        raise RuntimeError(
            "hnt-chat add failed:\n{}\n{}".format(
                add_res.stdout.strip(), add_res.stderr.strip()
            )
        )

    gen_res = subprocess.run(
        [
            "hnt-chat",
            "gen",
            "--output-filename",
            "--include-reasoning",
            "--model",
            LLM_MODEL_STRING,
            "-c",
            chat_id,
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if gen_res.returncode != 0:
        raise RuntimeError(
            "hnt-chat gen failed:\n{}\n{}".format(
                gen_res.stdout.strip(), gen_res.stderr.strip()
            )
        )

    output_name = gen_res.stdout.strip()
    if not output_name:
        raise RuntimeError("hnt-chat gen did not return an output filename")

    output_path = os.path.join(chat_id, output_name)
    with open(output_path, "r", encoding="utf-8") as handle:
        return handle.read()


def parse_commit_message(response_text):
    match = re.search(
        r"<commit_message>\s*(.*?)\s*</commit_message>",
        response_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not match:
        raise RuntimeError("LLM response missing <commit_message> block")
    message = match.group(1).strip()
    if not message:
        raise RuntimeError("LLM returned an empty commit message")
    return message


def generate_message_from_diff(diff_text, max_len, timeout_seconds):
    prompt_text = render_prompt(diff_text)
    response_text = run_hnt_chat(prompt_text, timeout_seconds)
    message = parse_commit_message(response_text)
    if max_len and len(message) > max_len:
        return message[:max_len]
    return message


def is_rebase_in_progress(repo):
    git_dir_res = run_git(["rev-parse", "--git-dir"], repo)
    git_dir = git_dir_res.stdout.strip()
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(repo, git_dir)
    return os.path.exists(os.path.join(git_dir, "rebase-merge")) or os.path.exists(
        os.path.join(git_dir, "rebase-apply")
    )


def abort_rebase(repo):
    subprocess.run(
        ["git", "rebase", "--abort"],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def rewrite_one(repo, regex, max_len, timeout_seconds):
    msg_res = run_git(["log", "-1", "--format=%B"], repo)
    message = msg_res.stdout.strip()
    if not re.search(regex, message):
        return 0

    diff_res = run_git(["show", "--format=", "--no-color", "HEAD"], repo)
    new_message = generate_message_from_diff(
        diff_res.stdout, max_len, timeout_seconds
    )

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


def rebase_rewrite(
    repo, regex, max_len, limit, allow_dirty, include_merges, timeout_seconds
):
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
        "--llm-timeout",
        str(timeout_seconds),
    ]
    x_cmd_str = " ".join(shlex.quote(part) for part in x_cmd)

    rebase_args = ["rebase", "--committer-date-is-author-date", "-x", x_cmd_str]
    if include_merges:
        rebase_args.insert(1, "--rebase-merges")

    if total <= limit:
        rebase_args.append("--root")
    else:
        rebase_args.append("HEAD~{}".format(limit))

    try:
        run_git(rebase_args, repo_root, capture=False, check=True)
    except Exception:
        if is_rebase_in_progress(repo_root):
            abort_rebase(repo_root)
        raise


def parse_args():
    parser = argparse.ArgumentParser(
        description="Rewrite matching commit messages in the last N commits."
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Path to the git repo.",
    )
    parser.add_argument(
        "--regex",
        default=r"20[0-9][0-9] hnt-tagme$",
        help="Regex to match commit messages for rewriting.",
    )
    parser.add_argument(
        "--max-len",
        type=int,
        default=0,
        help="Max length for commit messages (0 to disable).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Number of most recent commits to scan/rewrite.",
    )
    parser.add_argument(
        "--llm-timeout",
        type=int,
        default=DEFAULT_LLM_TIMEOUT,
        help="Timeout in seconds for the LLM generation step.",
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
    return parser, parser.parse_args()


def main():
    parser, args = parse_args()
    if args.repo is None:
        parser.print_help()
        return 1
    repo_root = get_repo_root(args.repo)

    if args.rewrite_one:
        try:
            return rewrite_one(
                repo_root, args.regex, args.max_len, args.llm_timeout
            )
        except Exception:
            if is_rebase_in_progress(repo_root):
                abort_rebase(repo_root)
            raise

    rebase_rewrite(
        repo_root,
        args.regex,
        args.max_len,
        args.limit,
        args.allow_dirty,
        include_merges=not args.no_merges,
        timeout_seconds=args.llm_timeout,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("error: {}".format(exc), file=sys.stderr)
        sys.exit(1)
