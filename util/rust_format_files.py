#!/usr/bin/env python3

import sys
import os
import subprocess
from pathlib import Path


def find_project_root(start_path: Path) -> Path | None:
    """
    Finds the Rust project root (directory with Cargo.toml) for a given path.
    """
    current_path = start_path.resolve()

    if not current_path.is_dir():
        current_path = current_path.parent

    while True:
        if (current_path / "Cargo.toml").is_file():
            return current_path

        if current_path.parent == current_path:  # Reached the root
            return None

        current_path = current_path.parent


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <file1.rs> [file2.rs ...]", file=sys.stderr)
        sys.exit(1)

    file_paths = sys.argv[1:]
    project_roots_to_format = set()

    for path_str in file_paths:
        path = Path(path_str)
        if not path.exists():
            print(f"Error: Path does not exist: {path}", file=sys.stderr)
            continue

        root = find_project_root(path)
        if root:
            project_roots_to_format.add(root)
        else:
            print(
                f"Warning: Could not find project root for {path}. Is it in a Cargo project?",
                file=sys.stderr,
            )

    if not project_roots_to_format:
        print("No Rust projects found to format.")
        return

    original_cwd = Path.cwd()
    for root in project_roots_to_format:
        print(f"==> Formatting project in {root}")
        try:
            os.chdir(root)
            result = subprocess.run(
                ["cargo", "fmt"], check=True, capture_output=True, text=True
            )
            # You can uncomment the following line to see the output from cargo fmt
            # if result.stdout: print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"Error running 'cargo fmt' in {root}:", file=sys.stderr)
            print(e.stderr, file=sys.stderr)
        except FileNotFoundError:
            print(
                "Error: 'cargo' command not found. Is Rust installed and in your PATH?",
                file=sys.stderr,
            )
            break
        except Exception as e:
            print(
                f"An unexpected error occurred while processing {root}: {e}",
                file=sys.stderr,
            )
        finally:
            os.chdir(original_cwd)

    print("Done.")


if __name__ == "__main__":
    main()
