# main.c – Quick Reference

High-level Goal  
Convert one or more files into an XML-like snippet that looks like:

```
<file_paths>
foo/bar.txt
baz.c
</file_paths>

<foo/bar.txt>
…binary-safe file contents…
</foo/bar.txt>

<baz.c>
…
</baz.c>
```

Optional behaviours are controlled by CLI flags and the whole output can be wrapped in markdown code-fences.

---

Major Components
================

Structs
• **FileInfo** – keeps absolute path, relative path (to a common root) and the file’s original argument order (orig_index).

Static Helpers
• **compareFileInfos** – qsort comparator on absolute paths (for the `-s` option).  
• **find_common_prefix** – derives the longest common directory prefix of two absolute paths; trims to directory boundary.  
• **print_file_content** – streams a file (opened in binary mode) to `stdout`, returns 1 if the last byte printed was `'\n'`.

Program Flow (`main`)
1. **Parse options**  
   `-n`  : suppress code-fence wrapping  
   `-p`  : print only the common root directory and exit  
   `-s`  : sort files by absolute path before printing

2. **Resolve absolute paths** with `realpath`, building an array of `FileInfo`.  
   While iterating, update **common_root** using `find_common_prefix`.

3. **Early exit** if `-p` was given (prints the common root).

4. **Optional sort** of `FileInfo` with `qsort` if `-s`.

5. **Build relative paths** by stripping `common_root` (+ ‘/’, unless root is “/”).  
   Falls back to `basename()` if anything looks wrong.

6. **Generate output**  
   • Optional opening code-fence  
   • `<file_paths>` list with relative paths  
   • For each file:  
     - `<rel_path>` tag  
     - stream file bytes via `print_file_content`  
     - ensure closing tag ends with exactly one newline  
   • Optional closing code-fence

7. **Cleanup** – free all allocated memory and exit.

---

Notable Details / Edge Handling
• Defines `_XOPEN_SOURCE 500` so `realpath` is available on stricter libc’s.  
• If `PATH_MAX` is missing it supplies a fallback of 4096.  
• All file I/O is binary (`"rb"`) to preserve arbitrary bytes.  
• Newline handling: adds a `\n` after a file’s contents only if the source file didn’t already end with one.  
• Emits warnings (to `stderr`) for non-fatal issues (failed opens, mismatched paths, etc.).  
• Ensures `common_root` never ends with a trailing ‘/’ (unless it is exactly “/”).  

This summary should give you enough context to navigate or modify `main.c` quickly.