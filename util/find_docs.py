#!/usr/bin/env python3
import os
import sys
from pathlib import Path


def find_impacted_docs(file_paths):
    """
    Given a list of modified file paths, find all potentially impacted
    documentation files by traversing up to the filesystem root.
    """
    potential_docs = set()
    for file_path_str in file_paths:
        file_path = Path(file_path_str).resolve()

        # B. more abstract: documentation for the file itself (e.g., foo.py.md)
        potential_docs.add(str(file_path) + ".md")

        # C. & D. more abstract: HINATA.md in the current and all parent directories
        current_dir = file_path.parent

        while True:
            # Add the HINATA.md for the current directory level
            potential_docs.add(str(current_dir / "HINATA.md"))

            # Stop condition: when we have reached the filesystem root
            if current_dir.parent == current_dir:
                break

            current_dir = current_dir.parent

    # All potential doc paths are absolute. Filter for the ones that exist.
    existing_docs = {doc for doc in potential_docs if os.path.exists(doc)}
    return sorted(list(existing_docs))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 find_docs.py <file1> <file2> ...", file=sys.stderr)
        sys.exit(1)

    modified_files = sys.argv[1:]
    impacted_docs = find_impacted_docs(modified_files)
    for doc in impacted_docs:
        print(doc)
