# hnt-apply.c – Quick Reference

CLI utility that **applies LLM-generated edit blocks** (TARGET/REPLACE) to a working
tree.  Intended to be called in a Unix pipeline, e.g.  
`llm-gen … | hnt-apply [-v] [--disallow-creating] [--ignore-reasoning] <files…>`

---

## High-level Flow (`main`)

1. **Parse CLI flags**  
   * `-v / --verbose` – chatty output  
   * `--disallow-creating` – forbid new files  
   * `--ignore-reasoning` – ignore initial `<think> … </think>` region

2. **Resolve absolute paths** of the file arguments.

3. **Run `llm-pack -p`** to compute a *shared project root* (path returned on
   stdout).  This lets the tool reference files relative to the root.

4. **Read stdin** (the LLM generation) into memory.

5. **Optionally strip `<think> … </think>`** when `--ignore-reasoning` is set.

6. **Scan stdin for edit blocks** with the exact structure:

   ```
   ```<newline>
   relative/path.ext<newline>
   <<<<<<< TARGET
   … target text …
   =======
   … replacement text …
   >>>>>>> REPLACE
   ``` (closing fence)
   ```

7. For every block call `process_block(…)`.

8. **Summarise success / failure** of all blocks and exit with `EXIT_SUCCESS`
   (all OK) or `EXIT_FAILURE`.

---

## Core Helpers

| Function | Purpose |
|----------|---------|
| `read_stream_to_string` | Slurp a FILE\* into a malloc’d buffer. |
| `run_command` | Run shell cmd, return trimmed stdout, exit on error. |
| `ensure_directory_exists` | `mkdir -p` equivalent for parent dirs. |
| `find_line_with_exact_content` | Utility used by block parser. |

---

## `process_block`

Input: root path, relative file path, *target*, *replace* strings.

1. **Build absolute path** (`root/rel_path`); attempt `realpath`.
2. **Creation path handling**  
   • If file does not exist and `target==""` and creation allowed → create file  
   • Otherwise abort with error.
3. **If file exists**  
   • Load file, count occurrences of *target*.  
   • Must appear **exactly once** (or zero if *target==""* and file empty).  
   • Replace it with *replace* and overwrite the file.
4. Return codes  
   * `0` – modified OK  
   * `1` – error  
   * `2` – created new file OK

---

## Global Flags

```
verbose_mode
disallow_creating_flag
ignore_reasoning_flag
```

---

## Exit Codes

* `0` – all blocks processed successfully
* `1` – at least one block failed

---

*File size ~1600 LOC, single translation unit, uses only libc & POSIX.*