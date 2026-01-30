#!/usr/bin/env python3
import argparse
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


LLM_MODEL_STRING = "openrouter/google/gemini-3-flash-preview"
PROMPT_TEMPLATE_NAME = "commit_message_prompt.md"
DEFAULT_LLM_TIMEOUT = 120


def run_git(args, cwd, capture=True, check=True, env=None):
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=capture,
        text=True,
        check=False,
        env=env,
    )
    if check and result.returncode != 0:
        stdout = result.stdout if result.stdout is not None else ""
        stderr = result.stderr if result.stderr is not None else ""
        raise RuntimeError(
            "git command failed: git {}\n{}\n{}".format(
                " ".join(args), stdout.strip(), stderr.strip()
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


def load_prompt_template(template_path=None):
    if template_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, PROMPT_TEMPLATE_NAME)
    with open(template_path, "r", encoding="utf-8") as handle:
        return handle.read()


def render_prompt(diff_text, template_path):
    template = load_prompt_template(template_path)
    if "__COMMIT_DIFF__" not in template:
        raise RuntimeError("prompt template missing __COMMIT_DIFF__ placeholder")
    return template.replace("__COMMIT_DIFF__", diff_text)


def truncate_diff_for_llm(diff_text):
    token_count = math.ceil(len(diff_text) / 5) if diff_text else 0
    if token_count < 50000:
        return diff_text

    keep_tokens = 20000
    keep_chars = keep_tokens * 5
    if len(diff_text) <= keep_chars * 2:
        return diff_text

    middle = diff_text[keep_chars:-keep_chars]
    lines_in_middle = middle.count("\n")
    notice = (
        "\n[... TRUNCATED middle of diff; {} more lines here ...]\n".format(
            lines_in_middle
        )
    )
    return diff_text[:keep_chars] + notice + diff_text[-keep_chars:]


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

    try:
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
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "hnt-chat gen timed out after {}s (model {}). Conversation: {}".format(
                timeout_seconds, LLM_MODEL_STRING, chat_id
            )
        ) from exc
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


def generate_message_from_diff(diff_text, max_len, timeout_seconds, template_path):
    prompt_text = render_prompt(truncate_diff_for_llm(diff_text), template_path)
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


def rewrite_one(repo, regex, max_len, timeout_seconds, template_path):
    msg_res = run_git(["log", "-1", "--format=%B"], repo)
    message = msg_res.stdout.strip()
    if not re.search(regex, message):
        return 0

    diff_res = run_git(["show", "--format=", "--no-color", "HEAD"], repo)
    new_message = generate_message_from_diff(
        diff_res.stdout, max_len, timeout_seconds, template_path
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


def prepare_runner_assets(prompt_template_path):
    temp_dir = tempfile.mkdtemp(prefix="hnt-rewrite-")
    script_src = os.path.abspath(__file__)
    script_dst = os.path.join(temp_dir, os.path.basename(script_src))
    shutil.copy2(script_src, script_dst)

    if prompt_template_path is None:
        prompt_src = os.path.join(
            os.path.dirname(script_src), PROMPT_TEMPLATE_NAME
        )
    else:
        prompt_src = os.path.abspath(prompt_template_path)
    prompt_dst = os.path.join(temp_dir, os.path.basename(prompt_src))
    shutil.copy2(prompt_src, prompt_dst)
    return temp_dir, script_dst, prompt_dst


def resolve_base(repo_root, limit):
    args = ["rev-list", "--reverse", "--max-count", str(limit), "HEAD"]
    res = run_git(args, repo_root)
    commits = [line.strip() for line in res.stdout.splitlines() if line.strip()]
    if not commits:
        return None, []
    root_parent = "{}^".format(commits[0])
    parent_check = run_git([ "rev-parse", root_parent ], repo_root, check=False)
    if parent_check.returncode != 0:
        return "--root", commits
    return root_parent, commits


def find_matching_commits(repo_root, base, regex, limit):
    if base == "--root":
        args = [
            "log",
            "--format=%H%x00%B%x1f",
            "--reverse",
            "--max-count",
            str(limit),
            "HEAD",
        ]
    else:
        args = [
            "log",
            "--format=%H%x00%B%x1f",
            "--reverse",
            "{}..HEAD".format(base),
        ]
    res = run_git(args, repo_root)
    entries = [e for e in res.stdout.split("\x1f") if e.strip()]
    matches = []
    for entry in entries:
        entry = entry.strip("\n")
        if not entry or "\x00" not in entry:
            continue
        sha, msg = entry.split("\x00", 1)
        if re.search(regex, msg.strip()):
            matches.append(sha.strip())
    return matches


def write_sequence_editor(matches, x_cmd_str):
    temp_dir = tempfile.mkdtemp(prefix="hnt-rewrite-todo-")
    script_path = os.path.join(temp_dir, "sequence_editor.py")
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(
            """#!/usr/bin/env python3
import os
import sys

full_matches = [m for m in os.environ.get("HNT_REWRITE_MATCHES", "").split() if m]
exec_line = os.environ.get("HNT_REWRITE_EXEC", "").strip()

todo_path = sys.argv[1]
with open(todo_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    new_lines.append(line)
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    parts = stripped.split()
    if parts and parts[0] in ("pick", "reword", "edit", "squash", "fixup"):
        sha = parts[1] if len(parts) > 1 else ""
        if any(full.startswith(sha) for full in full_matches):
            new_lines.append("exec " + exec_line + "\\n")

with open(todo_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)
"""
        )
    os.chmod(script_path, 0o755)
    return temp_dir, script_path


def rebase_rewrite(
    repo,
    regex,
    max_len,
    limit,
    allow_dirty,
    include_merges,
    timeout_seconds,
    prompt_template_path,
):
    repo_root = get_repo_root(repo)
    if not allow_dirty:
        ensure_clean(repo_root)

    base, commits = resolve_base(repo_root, limit)
    if base is None:
        return

    matches = find_matching_commits(repo_root, base, regex, limit)
    if not matches:
        return

    temp_dir, runner_script, runner_prompt = prepare_runner_assets(
        prompt_template_path
    )
    seq_dir = None
    try:
        x_cmd = [
            "python3",
            runner_script,
            "--rewrite-one",
            "--repo",
            repo_root,
            "--regex",
            regex,
            "--max-len",
            str(max_len),
            "--llm-timeout",
            str(timeout_seconds),
            "--prompt-template",
            runner_prompt,
        ]
        x_cmd_str = " ".join(shlex.quote(part) for part in x_cmd)

        seq_dir, seq_editor = write_sequence_editor(matches, x_cmd_str)

        if base == "--root":
            rebase_args = ["rebase", "-i", "--committer-date-is-author-date", "--root"]
        else:
            rebase_args = ["rebase", "-i", "--committer-date-is-author-date", base]
        if include_merges:
            rebase_args.insert(1, "--rebase-merges")

        env = os.environ.copy()
        env["GIT_SEQUENCE_EDITOR"] = seq_editor
        env["HNT_REWRITE_MATCHES"] = " ".join(matches)
        env["HNT_REWRITE_EXEC"] = x_cmd_str

        run_git(rebase_args, repo_root, capture=False, check=True, env=env)
    except Exception:
        if is_rebase_in_progress(repo_root):
            print(
                "warning: rebase paused; temp assets preserved in {}".format(
                    temp_dir
                ),
                file=sys.stderr,
            )
        raise
    finally:
        if not is_rebase_in_progress(repo_root):
            shutil.rmtree(temp_dir, ignore_errors=True)
            if seq_dir is not None:
                shutil.rmtree(seq_dir, ignore_errors=True)


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
        "--prompt-template",
        default=None,
        help="Path to the prompt template markdown file.",
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
                repo_root,
                args.regex,
                args.max_len,
                args.llm_timeout,
                args.prompt_template,
            )
        except Exception:
            raise

    rebase_rewrite(
        repo_root,
        args.regex,
        args.max_len,
        args.limit,
        args.allow_dirty,
        include_merges=not args.no_merges,
        timeout_seconds=args.llm_timeout,
        prompt_template_path=args.prompt_template,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("error: {}".format(exc), file=sys.stderr)
        sys.exit(1)
