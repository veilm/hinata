#!/usr/bin/env python3

import random
import string
import subprocess
import sys

# --- Configuration ---
NUM_TESTS = 2000
MIN_TOKENS = 1
MAX_TOKENS = 300
HNT_ESCAPE_CMD = "hnt-escape"  # Command to run the tool
# ---


def random_case(s):
    """Randomizes the casing of characters in a string."""
    return "".join(random.choice([c.lower(), c.upper()]) for c in s)


# List of functions, each generating a random token string
token_generators = [
    lambda: random.choice([" ", "\t", "\n", "\r"]),  # Whitespace
    lambda: random.choice(string.ascii_lowercase),  # Lowercase char
    lambda: random.choice(string.ascii_uppercase),  # Uppercase char
    lambda: random.choice(string.digits),  # Digit
    lambda: random.choice(["<", ">", "_", "-", "/"]),  # Specific symbols
    lambda: "hnt",  # "hnt" literal
    lambda: random_case("hnt"),  # "hnt" random case
    lambda: random.choice(["system", "user", "assistant"]),  # Role literal
    lambda: random_case(
        random.choice(["system", "user", "assistant"])
    ),  # Role random case
    lambda: random.choice(
        ["hnt-system", "hnt-user", "hnt-assistant"]
    ),  # hnt-role literal
    lambda: random.choice(
        ["/hnt-system", "/hnt-user", "/hnt-assistant"]
    ),  # /hnt-role literal
]

print(f"Starting round-trip escape/unescape tests for '{HNT_ESCAPE_CMD}'...")
print(f"Number of tests: {NUM_TESTS}")
print(f"Tokens per test: {MIN_TOKENS}-{MAX_TOKENS}")
print("-" * 30)

for i in range(NUM_TESTS):
    # Print progress
    if (i + 1) % 100 == 0 or i == 0:
        print(f"Running test {i + 1}/{NUM_TESTS}...")

    # 1. Generate random input
    num_tokens = random.randint(MIN_TOKENS, MAX_TOKENS)
    tokens = [random.choice(token_generators)() for _ in range(num_tokens)]
    original_input_str = "".join(tokens)
    # Use UTF-8 encoding for consistency, adjust if your tool expects something else
    original_input_bytes = original_input_str.encode("utf-8")

    # 2. Pipe input to hnt-escape (escape)
    try:
        escape_process = subprocess.run(
            [HNT_ESCAPE_CMD],
            input=original_input_bytes,
            capture_output=True,
            check=True,  # Raise CalledProcessError on non-zero exit code
        )
        escaped_output_bytes = escape_process.stdout
    except FileNotFoundError:
        print(f"\nError: Command '{HNT_ESCAPE_CMD}' not found.", file=sys.stderr)
        print(
            "Please ensure the hnt-escape tool is installed and in your system's PATH.",
            file=sys.stderr,
        )
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"\n--- TEST FAILED (Error during initial escape) ---", file=sys.stderr)
        print(f"Test number: {i + 1}", file=sys.stderr)
        print(f"Command: '{' '.join(e.cmd)}'", file=sys.stderr)
        print(f"Return code: {e.returncode}", file=sys.stderr)
        print("\nOriginal Input (bytes):", file=sys.stderr)
        print(original_input_bytes.decode("utf-8", errors="replace"), file=sys.stderr)
        # print(f"{original_input_bytes!r}", file=sys.stderr) # Raw bytes representation
        print("\nStderr:", file=sys.stderr)
        print(e.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(
            f"\n--- TEST FAILED (Unexpected error during escape) ---", file=sys.stderr
        )
        print(f"Test number: {i + 1}", file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        print("\nOriginal Input (bytes):", file=sys.stderr)
        print(original_input_bytes.decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(1)

    # 3. Pipe escaped output to hnt-escape -u (unescape)
    try:
        unescape_process = subprocess.run(
            [HNT_ESCAPE_CMD, "-u"],
            input=escaped_output_bytes,
            capture_output=True,
            check=True,  # Raise CalledProcessError on non-zero exit code
        )
        final_output_bytes = unescape_process.stdout
    except subprocess.CalledProcessError as e:
        print(f"\n--- TEST FAILED (Error during unescape) ---", file=sys.stderr)
        print(f"Test number: {i + 1}", file=sys.stderr)
        print(f"Command: '{' '.join(e.cmd)}'", file=sys.stderr)
        print(f"Return code: {e.returncode}", file=sys.stderr)
        print("\nOriginal Input (string):", file=sys.stderr)
        print(original_input_str, file=sys.stderr)
        print("\nInput to Unescape (Escaped Output - bytes):", file=sys.stderr)
        print(escaped_output_bytes.decode("utf-8", errors="replace"), file=sys.stderr)
        # print(f"{escaped_output_bytes!r}", file=sys.stderr) # Raw bytes representation
        print("\nStderr:", file=sys.stderr)
        print(e.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(
            f"\n--- TEST FAILED (Unexpected error during unescape) ---", file=sys.stderr
        )
        print(f"Test number: {i + 1}", file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        print("\nOriginal Input (string):", file=sys.stderr)
        print(original_input_str, file=sys.stderr)
        print("\nInput to Unescape (Escaped Output - bytes):", file=sys.stderr)
        print(escaped_output_bytes.decode("utf-8", errors="replace"), file=sys.stderr)
        sys.exit(1)

    # 4. Compare final output with original input (byte-for-byte)
    if final_output_bytes != original_input_bytes:
        print(f"\n--- TEST FAILED (Output Mismatch) ---")
        print(f"Test number: {i + 1}")

        # Try decoding for human-readable output, fall back to raw bytes if needed
        try:
            original_decoded = original_input_bytes.decode("utf-8")
            final_decoded = final_output_bytes.decode("utf-8")
            escaped_decoded = escaped_output_bytes.decode("utf-8")

            print("\nOriginal Input (decoded string):")
            print(original_decoded)
            print("\nEscaped Output (decoded string):")
            print(escaped_decoded)
            print("\nFinal Output (decoded string):")
            print(final_decoded)

        except UnicodeDecodeError:
            print(
                "\n(One or more strings could not be decoded as UTF-8, showing raw bytes)"
            )
            print("\nOriginal Input (bytes):")
            print(f"{original_input_bytes!r}")
            print("\nEscaped Output (bytes):")
            print(f"{escaped_output_bytes!r}")
            print("\nFinal Output (bytes):")
            print(f"{final_output_bytes!r}")

        # Provide byte counts for quick comparison
        print(
            f"\nByte Counts: Original={len(original_input_bytes)}, Escaped={len(escaped_output_bytes)}, Final={len(final_output_bytes)}"
        )

        sys.exit(1)  # Exit immediately on failure

# If loop completes without exiting
print("-" * 30)
print(f"--- ALL {NUM_TESTS} TESTS PASSED SUCCESSFULLY ---")
sys.exit(0)
