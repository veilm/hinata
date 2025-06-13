#!/usr/bin/env python3

import sys
import os
import subprocess
import time
import pathlib
import shutil
import tempfile


def main():
    # 1. Read JavaScript from stdin and wrap it in our console.log-based async executor.
    user_code = sys.stdin.read()
    js_input_code = f"""
// --- qb-eval wrapper ---
// This script is designed to be idempotent, so it can be run multiple times.

// One-time console hook setup
if (typeof window.qbe_eval_hooked === 'undefined') {{
    window.qbe_eval_hooked = true;

    const originalConsoleLog = console.log;
    const originalConsoleWarn = console.warn;
    const originalConsoleError = console.error;

    const formatArgs = (args) => {{
        return args.map(arg => {{
            if (typeof arg === 'object' && arg !== null) {{
                if (arg instanceof Error) {{
                    return arg.stack || String(arg);
                }}
                try {{
                    return JSON.stringify(arg, null, 2);
                }} catch (e) {{
                    return String(arg);
                }}
            }}
            return String(arg);
        }}).join(' ');
    }};

    console.log = function(...args) {{
        window.qbe_output_logs.push(formatArgs(args));
        // Optionally still call original for debugging in qutebrowser console
        originalConsoleLog.apply(console, args);
    }};

    console.warn = function(...args) {{
        window.qbe_output_logs.push('WARNING: ' + formatArgs(args));
        originalConsoleWarn.apply(console, args);
    }};

    console.error = function(...args) {{
        window.qbe_output_logs.push('ERROR: ' + formatArgs(args));
        originalConsoleError.apply(console, args);
    }};
}}

// Per-evaluation state
window.qbe_output_logs = [];
window.qbe_error = null;

// Wrap user code in an async IIFE to allow top-level await
window.qbe_promise = (async () => {{
    try {{
        // --- User code starts ---
{user_code}
        // --- User code ends ---
    }} catch (error) {{
        window.qbe_error = {{
            message: error.message,
            stack: error.stack,
            name: error.name
        }};
        // Also log the error to the output. We push the raw error string
        // instead of using console.error to avoid the "ERROR:" prefix for
        // uncaught exceptions.
        window.qbe_output_logs.push(error.stack || String(error));
    }}
    // The promise always resolves with the full log output.
    return window.qbe_output_logs.join('\\n');
}})();
// --- end qb-eval wrapper ---
"""

    # 2. Create a unique temporary directory
    # Using system's temp directory base and a subdirectory for our app
    base_temp_root = pathlib.Path(tempfile.gettempdir())
    app_temp_dir = base_temp_root / "qb-eval"

    timestamp_ns = time.time_ns()
    temp_dir_path = app_temp_dir / str(timestamp_ns)

    try:
        temp_dir_path.mkdir(parents=True, exist_ok=True)

        # 3. Write stdin to input.js
        input_js_path = temp_dir_path / "input.js"
        input_js_path.write_text(js_input_code)
        # print(f"DEBUG: Temp dir: {temp_dir_path}", file=sys.stderr)
        # print(f"DEBUG: Input JS path: {input_js_path}", file=sys.stderr)

        # 4. Run qutebrowser to execute input.js
        # This script should set window.qbe_out
        qutebrowser_cmd_input = [
            "qutebrowser",
            f":jseval -f -w main {input_js_path.resolve()}",
        ]
        # print(f"DEBUG: Executing: {' '.join(qutebrowser_cmd_input)}", file=sys.stderr)
        subprocess.run(
            qutebrowser_cmd_input,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 5. Create extract.js
        extract_js_content = """
(() => {
    // window.qbe_promise is always created by the input wrapper.
    // It resolves with the accumulated logs as a single string.
    const promise = window.qbe_promise;

    promise.then(outputContent => {
        if (typeof outputContent === 'undefined') {
            outputContent = 'undefined';
        } else if (outputContent === null) {
            outputContent = 'null';
        } else {
            outputContent = String(outputContent);
        }

        let blob = new Blob([outputContent], {type: 'text/plain'});
        let href = URL.createObjectURL(blob);

        let a = document.createElement('a');
        a.href = href;
        a.download = 'out.txt'; // Target filename for the download
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a); // Clean up the anchor element
        URL.revokeObjectURL(href);    // Release the object URL
    }).catch(error => {
        // This is a safeguard. The wrapper is designed to not reject the promise.
        console.error('qbe-eval promise was unexpectedly rejected:', error);
        const errorMessage = `Promise unexpectedly rejected in qbe-eval: ${error.stack || String(error)}`;
        let blob = new Blob([errorMessage], {type: 'text/plain'});
        let href = URL.createObjectURL(blob);
        let a = document.createElement('a');
        a.href = href;
        a.download = 'out.txt';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(href);
    });
})();
"""
        extract_js_path = temp_dir_path / "extract.js"
        extract_js_path.write_text(extract_js_content)
        # print(f"DEBUG: Extract JS path: {extract_js_path}", file=sys.stderr)

        # 6. Run qutebrowser to execute extract.js and trigger download
        abs_temp_dir_path_str = str(temp_dir_path.resolve())

        # Ensure paths with spaces are handled if qutebrowser needs quoting internally,
        # but Python's list2cmdline usually handles this for subprocess.
        # For qutebrowser commands, it's safer if paths don't have spaces,
        # but temp dir names usually don't.
        qutebrowser_cmd_extract = [
            "qutebrowser",
            f":set downloads.location.directory {abs_temp_dir_path_str} ;; "
            f"set downloads.location.prompt false ;; "
            f"set downloads.remove_finished 0 ;; "
            f"jseval -f -w main {extract_js_path.resolve()}",
        ]
        # print(f"DEBUG: Executing: {' '.join(qutebrowser_cmd_extract)}", file=sys.stderr)
        subprocess.run(
            qutebrowser_cmd_extract,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # 7. Wait for out.txt to appear, then read it and write to stdout
        output_file_path = temp_dir_path / "out.txt"
        timeout_seconds = 180  # Max time to wait for the file

        try:
            wait_cmd = ["wait_until_file", str(output_file_path), str(timeout_seconds)]
            result = subprocess.run(
                wait_cmd,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            print(
                "Error: 'wait_until_file' command not found. Is it in your PATH? Please run the build script.",
                file=sys.stderr,
            )
            sys.exit(1)

        # wait_until_file returns:
        # 1: file found
        # 2: timeout
        # 3: bad args
        # 4: other error
        if result.returncode != 1:
            print(
                f"Error waiting for output file. wait_until_file exited with {result.returncode}.",
                file=sys.stderr,
            )
            if result.stderr:
                # The C program prints descriptive errors to stderr
                sys.stderr.write(result.stderr)
            sys.exit(1)

        # Small delay to allow file system to catch up / qutebrowser to finish writing
        time.sleep(0.2)

        output_content = output_file_path.read_text()
        sys.stdout.write(output_content)
        sys.stdout.flush()

    except subprocess.CalledProcessError as e:
        print(f"Error during qutebrowser execution.", file=sys.stderr)
        print(f"Command: {e.cmd}", file=sys.stderr)
        if e.stdout:
            print(f"Stdout: {e.stdout.decode(errors='replace')}", file=sys.stderr)
        if e.stderr:
            print(f"Stderr: {e.stderr.decode(errors='replace')}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(
            "Error: 'qutebrowser' command not found. Is it installed and in your PATH?",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # 8. Cleanup the temporary directory
        if temp_dir_path.exists():
            try:
                shutil.rmtree(temp_dir_path)
                # print(f"DEBUG: Cleaned up {temp_dir_path}", file=sys.stderr)
            except Exception as e:
                print(
                    f"Warning: Failed to clean up temporary directory {temp_dir_path}: {e}",
                    file=sys.stderr,
                )


if __name__ == "__main__":
    # Make sure qutebrowser is running, or this script will try to start it.
    # For best results, have a qutebrowser session open.
    main()
