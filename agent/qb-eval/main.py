#!/usr/bin/env python3

import sys
import os
import subprocess
import time
import pathlib
import shutil
import tempfile


def main():
    # 1. Read JavaScript from stdin
    js_input_code = sys.stdin.read()

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
        extract_js_content = f"""
(() => {{
    let outputContent = window.qbe_out;

    if (typeof outputContent === 'undefined') {{
        outputContent = 'undefined';
    }} else if (outputContent === null) {{
        outputContent = 'null';
    }} else {{
        outputContent = String(outputContent);
    }}

    let blob = new Blob([outputContent], {{type: 'text/plain'}});
    let href = URL.createObjectURL(blob);

    let a = document.createElement('a');
    a.href = href;
    a.download = 'out.txt'; // Target filename for the download
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a); // Clean up the anchor element
    URL.revokeObjectURL(href);    // Release the object URL
}})();
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

        # timeout_seconds = 10  # Max time to wait for the file
        timeout_seconds = 180  # Max time to wait for the file
        poll_interval = 1  # Time between checks
        start_wait_time = time.monotonic()

        while not output_file_path.exists():
            if time.monotonic() - start_wait_time > timeout_seconds:
                print(
                    f"Error: Output file '{output_file_path}' not found after {timeout_seconds} seconds.",
                    file=sys.stderr,
                )
                # print(f"DEBUG: Check if qutebrowser is running and responsive.", file=sys.stderr)
                sys.exit(1)
            time.sleep(poll_interval)

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
