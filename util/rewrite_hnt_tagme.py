#!/usr/bin/env python3
import argparse
import json
import math
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass


LLM_MODEL_STRING = "openrouter/google/gemini-3-flash-preview"
PROMPT_TEMPLATE_NAME = "commit_message_prompt.md"
DEFAULT_LLM_TIMEOUT = 120
TEXT_ENCODING = "utf-8"
TEXT_ERRORS = "replace"
COAUTHOR_TRAILER = "Co-Authored-By: Hinata <veil@sucralose.moe>"


@dataclass
class CommitObject:
    sha: str
    parents: list
    tree: str
    headers: list
    message: bytes

    def header_value(self, name):
        name_bytes = name.encode("ascii")
        for key, lines in self.headers:
            if key == name_bytes:
                _, _, value = lines[0].partition(b" ")
                return value
        return None

    def has_header(self, name):
        name_bytes = name.encode("ascii")
        return any(key == name_bytes for key, _ in self.headers)


def format_command(args):
    return " ".join(shlex.quote(str(arg)) for arg in args)


def run_git(
    args,
    cwd,
    capture=True,
    check=True,
    env=None,
    timeout=None,
    input_text=None,
):
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=capture,
        text=True,
        encoding=TEXT_ENCODING,
        errors=TEXT_ERRORS,
        check=False,
        env=env,
        timeout=timeout,
        input=input_text,
    )
    if check and result.returncode != 0:
        stdout = result.stdout if result.stdout is not None else ""
        stderr = result.stderr if result.stderr is not None else ""
        raise RuntimeError(
            "git command failed: git {}\n{}\n{}".format(
                format_command(args), stdout.strip(), stderr.strip()
            )
        )
    return result


def run_git_bytes(args, cwd, input_data=None, check=True):
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        check=False,
        input=input_data,
    )
    if check and result.returncode != 0:
        stdout = result.stdout.decode(TEXT_ENCODING, errors=TEXT_ERRORS)
        stderr = result.stderr.decode(TEXT_ENCODING, errors=TEXT_ERRORS)
        raise RuntimeError(
            "git command failed: git {}\n{}\n{}".format(
                format_command(args), stdout.strip(), stderr.strip()
            )
        )
    return result


def get_repo_root(repo):
    res = run_git(["rev-parse", "--show-toplevel"], repo)
    return os.path.abspath(res.stdout.strip())


def get_git_dir(repo_root):
    res = run_git(["rev-parse", "--git-dir"], repo_root)
    git_dir = res.stdout.strip()
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(repo_root, git_dir)
    return os.path.abspath(git_dir)


def get_head_ref(repo_root):
    res = run_git(["symbolic-ref", "--quiet", "HEAD"], repo_root, check=False)
    if res.returncode == 0 and res.stdout.strip():
        return res.stdout.strip()
    return "HEAD"


def get_head_sha(repo_root, ref="HEAD"):
    return run_git(["rev-parse", "--verify", ref], repo_root).stdout.strip()


def ensure_no_operation_in_progress(repo_root, git_dir):
    markers = [
        "rebase-merge",
        "rebase-apply",
        "sequencer",
        "MERGE_HEAD",
        "CHERRY_PICK_HEAD",
        "REVERT_HEAD",
        "BISECT_LOG",
    ]
    active = [
        marker for marker in markers if os.path.exists(os.path.join(git_dir, marker))
    ]
    if active:
        raise RuntimeError(
            "another Git operation is already in progress: {}".format(
                ", ".join(active)
            )
        )


def ensure_tracked_clean(repo_root):
    res = run_git(
        ["status", "--porcelain", "--untracked-files=no"],
        repo_root,
    )
    if res.stdout.strip():
        raise RuntimeError(
            "tracked working-tree or index changes exist; commit or stash them first "
            "(ignored and untracked files are not touched by this rewrite)"
        )


def load_prompt_template(template_path=None):
    if template_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, PROMPT_TEMPLATE_NAME)
    with open(
        template_path,
        "r",
        encoding=TEXT_ENCODING,
        errors=TEXT_ERRORS,
    ) as handle:
        return handle.read()


def render_prompt(diff_text, template_text):
    if "__COMMIT_DIFF__" not in template_text:
        raise RuntimeError("prompt template missing __COMMIT_DIFF__ placeholder")
    return template_text.replace("__COMMIT_DIFF__", diff_text)


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
    try:
        chat_res = subprocess.run(
            ["hnt-chat", "new"],
            capture_output=True,
            text=True,
            encoding=TEXT_ENCODING,
            errors=TEXT_ERRORS,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "hnt-chat new timed out after {}s".format(timeout_seconds)
        ) from exc
    if chat_res.returncode != 0:
        raise RuntimeError(
            "hnt-chat new failed:\n{}\n{}".format(
                chat_res.stdout.strip(), chat_res.stderr.strip()
            )
        )
    chat_id = chat_res.stdout.strip()
    if not chat_id or "\n" in chat_id:
        raise RuntimeError(
            "hnt-chat new returned an invalid conversation path: {!r}".format(
                chat_id
            )
        )

    try:
        add_res = subprocess.run(
            ["hnt-chat", "add", "user", "-c", chat_id],
            input=prompt_text,
            capture_output=True,
            text=True,
            encoding=TEXT_ENCODING,
            errors=TEXT_ERRORS,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "hnt-chat add timed out after {}s (conversation {})".format(
                timeout_seconds, chat_id
            )
        ) from exc
    if add_res.returncode != 0:
        raise RuntimeError(
            "hnt-chat add failed for {}:\n{}\n{}".format(
                chat_id, add_res.stdout.strip(), add_res.stderr.strip()
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
            encoding=TEXT_ENCODING,
            errors=TEXT_ERRORS,
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
            "hnt-chat gen failed for {}:\n{}\n{}".format(
                chat_id, gen_res.stdout.strip(), gen_res.stderr.strip()
            )
        )

    output_name = gen_res.stdout.strip()
    if not output_name or "\n" in output_name:
        raise RuntimeError(
            "hnt-chat gen returned an invalid output filename for {}: {!r}".format(
                chat_id, output_name
            )
        )

    chat_dir = os.path.abspath(chat_id)
    output_path = os.path.abspath(os.path.join(chat_dir, output_name))
    if os.path.commonpath([chat_dir, output_path]) != chat_dir:
        raise RuntimeError(
            "hnt-chat returned an output path outside its conversation: {}".format(
                output_name
            )
        )
    with open(
        output_path,
        "r",
        encoding=TEXT_ENCODING,
        errors=TEXT_ERRORS,
    ) as handle:
        return handle.read(), chat_dir


def parse_commit_message(response_text):
    matches = re.findall(
        r"<commit_message>\s*(.*?)\s*</commit_message>",
        response_text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not matches:
        raise RuntimeError("LLM response missing <commit_message> block")
    if len(matches) != 1:
        raise RuntimeError("LLM response contained multiple <commit_message> blocks")
    message = matches[0].strip()
    if not message:
        raise RuntimeError("LLM returned an empty commit message")
    return message


def normalize_commit_message(message, max_len):
    if "\x00" in message:
        raise RuntimeError("LLM returned a commit message containing NUL bytes")

    cleaned_lines = []
    trailer_folded = COAUTHOR_TRAILER.casefold()
    for line in message.strip().splitlines():
        if line.strip().casefold() == trailer_folded:
            continue
        cleaned_lines.append(line.rstrip())

    body = "\n".join(cleaned_lines).strip()
    if not body:
        raise RuntimeError("LLM returned an empty commit message")

    normalized = body + "\n\n" + COAUTHOR_TRAILER + "\n"
    if max_len and len(normalized) > max_len:
        raise RuntimeError(
            "LLM returned a {}-character message, exceeding --max-len {}".format(
                len(normalized), max_len
            )
        )
    return normalized


def decode_commit_message(commit):
    encoding = commit.header_value("encoding")
    if encoding:
        try:
            codec = encoding.decode("ascii")
            return commit.message.decode(codec, errors=TEXT_ERRORS)
        except (LookupError, UnicodeError):
            pass
    return commit.message.decode(TEXT_ENCODING, errors=TEXT_ERRORS)


def generate_message_from_diff(
    diff_text,
    max_len,
    timeout_seconds,
    template_text,
):
    prompt_text = render_prompt(truncate_diff_for_llm(diff_text), template_text)
    response_text, chat_dir = run_hnt_chat(prompt_text, timeout_seconds)
    message = normalize_commit_message(
        parse_commit_message(response_text),
        max_len,
    )
    return message, chat_dir


def parse_commit_object(sha, raw):
    header, separator, message = raw.partition(b"\n\n")
    if not separator:
        raise RuntimeError("commit {} has no header/message separator".format(sha))

    entries = []
    current = None
    for line in header.split(b"\n"):
        if line.startswith(b" "):
            if current is None:
                raise RuntimeError("commit {} has an orphaned header continuation".format(sha))
            current[1].append(line)
            continue

        key, separator, _ = line.partition(b" ")
        if not separator or not key:
            raise RuntimeError("commit {} has a malformed header".format(sha))
        current = [key, [line]]
        entries.append(current)

    def values(name):
        name_bytes = name.encode("ascii")
        result = []
        for key, lines in entries:
            if key == name_bytes:
                _, _, value = lines[0].partition(b" ")
                result.append(value)
        return result

    trees = values("tree")
    authors = values("author")
    committers = values("committer")
    if len(trees) != 1 or len(authors) != 1 or len(committers) != 1:
        raise RuntimeError("commit {} is missing standard headers".format(sha))

    parents = [value.decode("ascii") for value in values("parent")]
    return CommitObject(
        sha=sha,
        parents=parents,
        tree=trees[0].decode("ascii"),
        headers=[(key, list(lines)) for key, lines in entries],
        message=message,
    )


def load_commit_graph(repo_root):
    graph_res = run_git(
        ["rev-list", "--topo-order", "--reverse", "--parents", "HEAD"],
        repo_root,
    )
    graph_lines = [
        line.split()
        for line in graph_res.stdout.splitlines()
        if line.strip()
    ]
    if not graph_lines:
        raise RuntimeError("repository has no commits")

    shas = [parts[0] for parts in graph_lines]
    request = b"".join((sha.encode("ascii") + b"\n") for sha in shas)
    batch_res = run_git_bytes(["cat-file", "--batch"], repo_root, request)

    objects = {}
    offset = 0
    for index, expected_sha in enumerate(shas):
        header_end = batch_res.stdout.find(b"\n", offset)
        if header_end == -1:
            raise RuntimeError("git cat-file --batch returned a truncated header")
        header_parts = batch_res.stdout[offset:header_end].split()
        offset = header_end + 1
        if len(header_parts) != 3 or header_parts[0].decode("ascii") != expected_sha:
            raise RuntimeError("git cat-file --batch returned an unexpected object")
        object_type = header_parts[1]
        if object_type != b"commit":
            raise RuntimeError("{} is not a commit object".format(expected_sha))
        size = int(header_parts[2])
        raw = batch_res.stdout[offset : offset + size]
        if len(raw) != size:
            raise RuntimeError("git cat-file --batch returned a truncated object")
        offset += size
        if batch_res.stdout[offset : offset + 1] != b"\n":
            raise RuntimeError("git cat-file --batch object separator is missing")
        offset += 1

        commit = parse_commit_object(expected_sha, raw)
        expected_parents = graph_lines[index][1:]
        if commit.parents != expected_parents:
            raise RuntimeError(
                "parent list mismatch while reading commit {}".format(expected_sha)
            )
        objects[expected_sha] = commit

    return objects, shas


def get_first_parent_candidates(objects, old_tip, limit, regex):
    candidates = []
    current = old_tip
    for _ in range(limit):
        commit = objects.get(current)
        if commit is None:
            break
        if regex.search(decode_commit_message(commit).strip()):
            candidates.append(current)
        if not commit.parents:
            break
        current = commit.parents[0]
    candidates.reverse()
    return candidates


def get_commit_diff(repo_root, commit):
    if len(commit.parents) > 1:
        args = [
            "diff-tree",
            "--no-commit-id",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            "-p",
            commit.parents[0],
            commit.sha,
        ]
    else:
        args = [
            "show",
            "--format=",
            "--no-color",
            "--no-ext-diff",
            "--no-textconv",
            commit.sha,
        ]
    return run_git(args, repo_root).stdout


def write_json_atomic(path, data):
    directory = os.path.dirname(path)
    fd, temp_path = tempfile.mkstemp(
        prefix=".tmp-",
        suffix=".json",
        dir=directory,
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding=TEXT_ENCODING) as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass
        raise


def create_manifest(repo_root, git_dir, run_id, old_tip, target_ref, limit, regex):
    manifest_dir = os.path.join(git_dir, "hnt-tagme-rewrite", run_id)
    os.makedirs(manifest_dir, exist_ok=False)
    manifest_path = os.path.join(manifest_dir, "plan.json")
    manifest = {
        "version": 1,
        "status": "planning",
        "run_id": run_id,
        "old_tip": old_tip,
        "target_ref": target_ref,
        "limit": limit,
        "selection": "first-parent",
        "regex": regex,
        "messages": {},
    }
    write_json_atomic(manifest_path, manifest)
    return manifest_dir, manifest_path, manifest


def update_manifest(manifest_path, manifest, status=None, error=None):
    if status is not None:
        manifest["status"] = status
    if error is not None:
        manifest["error"] = str(error)
    write_json_atomic(manifest_path, manifest)


def calculate_rewrite_closure(objects, order, replacements):
    changed = set()
    for sha in order:
        commit = objects[sha]
        replacement = replacements.get(sha)
        message_changed = replacement is not None and (
            replacement.encode(TEXT_ENCODING) != commit.message
        )
        parent_changed = any(parent in changed for parent in commit.parents)
        if message_changed or parent_changed:
            changed.add(sha)
    return changed


def get_header_value_bytes(commit, name):
    return commit.header_value(name)


def build_rewritten_commit(
    commit,
    mapped_parents,
    replacement_message,
    allow_signature_loss,
):
    message_changed = replacement_message is not None
    message = (
        replacement_message.encode(TEXT_ENCODING)
        if message_changed
        else commit.message
    )
    if message_changed and not message.endswith(b"\n"):
        message += b"\n"

    output_lines = []
    inserted_parents = False
    for key, lines in commit.headers:
        if key == b"parent":
            if not inserted_parents:
                output_lines.extend(
                    b"parent " + parent.encode("ascii") for parent in mapped_parents
                )
                inserted_parents = True
            continue

        if key == b"gpgsig":
            if not allow_signature_loss:
                raise RuntimeError(
                    "commit {} is signed and must be rewritten; rerun with "
                    "--allow-signature-loss to strip its invalid signature".format(
                        commit.sha
                    )
                )
            continue

        if key == b"encoding" and message_changed:
            encoding = get_header_value_bytes(commit, "encoding")
            if encoding is None or encoding.casefold() != b"utf-8":
                continue

        output_lines.extend(lines)

    if mapped_parents and not inserted_parents:
        tree_index = next(
            index
            for index, (key, _) in enumerate(commit.headers)
            if key == b"tree"
        )
        output_lines[tree_index + 1 : tree_index + 1] = [
            b"parent " + parent.encode("ascii") for parent in mapped_parents
        ]

    return b"\n".join(output_lines) + b"\n\n" + message


def write_commit_object(repo_root, raw):
    result = run_git_bytes(
        ["hash-object", "-t", "commit", "-w", "--stdin"],
        repo_root,
        input_data=raw,
    )
    sha = result.stdout.decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]+", sha):
        raise RuntimeError("git hash-object returned an invalid commit ID: {}".format(sha))
    return sha


def build_rewritten_graph(
    repo_root,
    objects,
    order,
    replacements,
    allow_signature_loss,
):
    changed_closure = calculate_rewrite_closure(objects, order, replacements)
    if not changed_closure:
        return {}, {}, changed_closure

    for sha in changed_closure:
        commit = objects[sha]
        if commit.has_header("mergetag"):
            raise RuntimeError(
                "commit {} has a mergetag and is in the rewrite closure; "
                "refusing to rewrite it".format(sha)
            )
        if commit.has_header("gpgsig") and not allow_signature_loss:
            raise RuntimeError(
                "commit {} is signed and is in the rewrite closure; rerun with "
                "--allow-signature-loss to strip invalid signatures".format(sha)
            )

    mapping = {}
    generated_raw = {}
    for sha in order:
        commit = objects[sha]
        mapped_parents = []
        for parent in commit.parents:
            if parent in objects and parent not in mapping:
                raise RuntimeError(
                    "commit graph order did not place parent {} before {}".format(
                        parent, sha
                    )
                )
            mapped_parents.append(mapping.get(parent, parent))

        replacement = replacements.get(sha)
        message_changed = replacement is not None and (
            replacement.encode(TEXT_ENCODING) != commit.message
        )
        parent_changed = mapped_parents != commit.parents
        if not message_changed and not parent_changed:
            mapping[sha] = sha
            continue

        raw = build_rewritten_commit(
            commit,
            mapped_parents,
            replacement if message_changed else None,
            allow_signature_loss,
        )
        new_sha = write_commit_object(repo_root, raw)
        mapping[sha] = new_sha
        generated_raw[sha] = raw

    return mapping, generated_raw, changed_closure


def verify_rewritten_graph(
    repo_root,
    objects,
    order,
    mapping,
    generated_raw,
    replacements,
):
    for sha, raw in generated_raw.items():
        old_commit = objects[sha]
        new_commit = parse_commit_object(mapping[sha], raw)
        expected_parents = [
            mapping.get(parent, parent) for parent in old_commit.parents
        ]
        if new_commit.tree != old_commit.tree:
            raise RuntimeError("tree changed while rewriting commit {}".format(sha))
        if new_commit.parents != expected_parents:
            raise RuntimeError("parents changed unexpectedly for commit {}".format(sha))

        expected_message = replacements.get(sha)
        if expected_message is None:
            expected_message = old_commit.message.decode(
                TEXT_ENCODING,
                errors=TEXT_ERRORS,
            )
            expected_message_bytes = old_commit.message
        else:
            expected_message_bytes = expected_message.encode(TEXT_ENCODING)
            if not expected_message_bytes.endswith(b"\n"):
                expected_message_bytes += b"\n"
        if new_commit.message != expected_message_bytes:
            raise RuntimeError("message changed unexpectedly for commit {}".format(sha))

        for header_name in ("author", "committer"):
            if new_commit.header_value(header_name) != old_commit.header_value(header_name):
                raise RuntimeError(
                    "{} metadata changed while rewriting commit {}".format(
                        header_name, sha
                    )
                )

    old_tip = order[-1]
    new_tip = mapping.get(old_tip, old_tip)
    old_tree = objects[old_tip].tree
    new_tree = run_git(
        ["rev-parse", "{}^{{tree}}".format(new_tip)],
        repo_root,
    ).stdout.strip()
    if old_tree != new_tree:
        raise RuntimeError("rewritten HEAD tree differs from the original HEAD tree")
    return new_tip


def update_ref_atomically(repo_root, target_ref, old_tip, new_tip, backup_ref):
    transaction = (
        "start\n"
        "create {backup} {old}\n"
        "update {target} {new} {old}\n"
        "prepare\n"
        "commit\n"
    ).format(
        backup=backup_ref,
        target=target_ref,
        new=new_tip,
        old=old_tip,
    )
    run_git(["update-ref", "--stdin"], repo_root, input_text=transaction)


def rewrite_history(
    repo,
    regex_text,
    max_len,
    limit,
    allow_dirty,
    timeout_seconds,
    prompt_template_path,
    allow_signature_loss,
):
    repo_root = get_repo_root(repo)
    git_dir = get_git_dir(repo_root)
    ensure_no_operation_in_progress(repo_root, git_dir)
    if not allow_dirty:
        ensure_tracked_clean(repo_root)

    if limit <= 0:
        raise RuntimeError("--limit must be greater than zero")
    if timeout_seconds <= 0:
        raise RuntimeError("--llm-timeout must be greater than zero")
    if max_len < 0:
        raise RuntimeError("--max-len must be zero or greater")

    regex = re.compile(regex_text)
    target_ref = get_head_ref(repo_root)
    old_tip = get_head_sha(repo_root, target_ref if target_ref != "HEAD" else "HEAD")
    objects, order = load_commit_graph(repo_root)
    candidates = get_first_parent_candidates(objects, old_tip, limit, regex)
    if not candidates:
        print("no matching commits found")
        return 0

    run_id = "{}-{}".format(time.time_ns(), os.getpid())
    manifest_dir, manifest_path, manifest = create_manifest(
        repo_root,
        git_dir,
        run_id,
        old_tip,
        target_ref,
        limit,
        regex_text,
    )
    manifest["candidate_shas"] = candidates
    manifest["total_reachable_commits"] = len(order)
    update_manifest(manifest_path, manifest)

    try:
        template_text = load_prompt_template(prompt_template_path)
        replacements = {}
        for sha in candidates:
            diff_text = get_commit_diff(repo_root, objects[sha])
            message, chat_dir = generate_message_from_diff(
                diff_text,
                max_len,
                timeout_seconds,
                template_text,
            )
            replacements[sha] = message
            manifest["messages"][sha] = {
                "chat_directory": chat_dir,
                "message": message,
            }
            update_manifest(manifest_path, manifest)

        manifest["status"] = "planned"
        update_manifest(manifest_path, manifest)

        mapping, generated_raw, changed_closure = build_rewritten_graph(
            repo_root,
            objects,
            order,
            replacements,
            allow_signature_loss,
        )
        manifest["rewrite_closure_count"] = len(changed_closure)
        manifest["created_commit_count"] = len(generated_raw)
        update_manifest(manifest_path, manifest)

        new_tip = verify_rewritten_graph(
            repo_root,
            objects,
            order,
            mapping,
            generated_raw,
            replacements,
        )
        if new_tip == old_tip:
            manifest["status"] = "no-change"
            update_manifest(manifest_path, manifest)
            print("generated messages matched existing messages; no ref update needed")
            return 0

        backup_ref = "refs/hnt-tagme/backups/{}".format(run_id)
        current_ref = get_head_ref(repo_root)
        current_tip = get_head_sha(
            repo_root,
            current_ref if current_ref != "HEAD" else "HEAD",
        )
        if current_ref != target_ref or current_tip != old_tip:
            raise RuntimeError(
                "HEAD or its ref moved while messages were being generated; "
                "nothing was updated"
            )
        manifest["status"] = "ready-to-apply"
        manifest["new_tip"] = new_tip
        manifest["backup_ref"] = backup_ref
        update_manifest(manifest_path, manifest)
        update_ref_atomically(repo_root, target_ref, old_tip, new_tip, backup_ref)
        try:
            manifest["status"] = "applied"
            update_manifest(manifest_path, manifest)
        except Exception as exc:
            print(
                "warning: ref update succeeded but audit manifest could not be "
                "marked applied: {}".format(exc),
                file=sys.stderr,
            )
        print(
            "rewrote {} commit message(s); new tip {}".format(
                len(replacements), new_tip
            )
        )
        print("backup ref: {}".format(backup_ref))
        print("audit manifest: {}".format(os.path.join(manifest_dir, "plan.json")))
        return 0
    except Exception as exc:
        try:
            update_manifest(manifest_path, manifest, status="failed", error=exc)
        except Exception as manifest_exc:
            print(
                "warning: could not update audit manifest: {}".format(manifest_exc),
                file=sys.stderr,
            )
        raise


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite matching recent commit messages without checking out or "
            "rebasing the working tree."
        )
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
        help="Maximum complete message length (0 to disable; oversized output fails).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Number of recent first-parent commits to scan.",
    )
    parser.add_argument(
        "--llm-timeout",
        type=int,
        default=DEFAULT_LLM_TIMEOUT,
        help="Timeout in seconds for each hnt-chat subprocess.",
    )
    parser.add_argument(
        "--prompt-template",
        default=None,
        help="Path to the prompt template markdown file.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help=(
            "Allow tracked changes; this object-only rewrite does not touch the "
            "working tree."
        ),
    )
    parser.add_argument(
        "--allow-signature-loss",
        action="store_true",
        help="Allow invalid gpgsig headers to be stripped from rewritten commits.",
    )
    return parser, parser.parse_args()


def main():
    parser, args = parse_args()
    if args.repo is None:
        parser.print_help()
        return 1
    rewrite_history(
        args.repo,
        args.regex,
        args.max_len,
        args.limit,
        args.allow_dirty,
        args.llm_timeout,
        args.prompt_template,
        args.allow_signature_loss,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("error: {}".format(exc), file=sys.stderr)
        sys.exit(1)
