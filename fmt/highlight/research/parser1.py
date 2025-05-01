# Import necessary libraries
import sys
import re
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer
    from pygments.formatters import TerminalTrueColorFormatter
    from pygments.util import ClassNotFound
    PYGMENTS_AVAILABLE = True
except ImportError:
    PYGMENTS_AVAILABLE = False
    print("Warning: 'pygments' library not found. Code block syntax highlighting will be disabled.", file=sys.stderr)
    print("Install it using: pip install Pygments", file=sys.stderr)


# --- Configuration ---
# Use a default style for syntax highlighting (requires pygments)
SYNTAX_STYLE = 'monokai'

# --- State Variables ---
in_code_block = False
code_language = None
code_buffer = ""

# --- Regex ---
# Regex to detect the start of a fenced code block (e.g., ```python)
code_block_start_re = re.compile(r"^\s*```\s*(\w+)?\s*$")
# Regex to detect the end of a fenced code block (```)
code_block_end_re = re.compile(r"^\s*```\s*$")


# --- Main Processing Function ---
def process_line(line):
    """Processes a single line of input for Markdown highlighting."""
    global in_code_block, code_language, code_buffer

    # Check if we are inside a code block
    if in_code_block:
        # Check if this line ends the code block
        if code_block_end_re.match(line):
            in_code_block = False
            # Highlight and print the buffered code if pygments is available
            if PYGMENTS_AVAILABLE:
                try:
                    if code_language:
                        try:
                            lexer = get_lexer_by_name(code_language)
                        except ClassNotFound:
                            print(f"(Could not find lexer for '{code_language}', guessing)", file=sys.stderr)
                            lexer = guess_lexer(code_buffer)
                    else:
                        # Guess the lexer if no language was specified
                        lexer = guess_lexer(code_buffer)

                    # Choose a formatter (TerminalTrueColorFormatter provides good colors)
                    formatter = TerminalTrueColorFormatter(style=SYNTAX_STYLE)
                    highlighted_code = highlight(code_buffer, lexer, formatter)
                    # Print the highlighted code, removing the trailing newline added by highlight
                    print(highlighted_code.rstrip('\n'), flush=True)

                except Exception as e:
                    # Fallback: print raw code if highlighting fails
                    print(f"(Highlighting failed: {e})", file=sys.stderr)
                    print(code_buffer, end='', flush=True)
            else:
                 # Fallback: print raw code if pygments is not installed
                 print(code_buffer, end='', flush=True)


            # Reset code block state
            code_buffer = ""
            code_language = None
        else:
            # Add the line to the code buffer
            code_buffer += line
    else:
        # Check if this line starts a code block
        match = code_block_start_re.match(line)
        if match:
            in_code_block = True
            # Store the specified language (if any)
            code_language = match.group(1)
            code_buffer = "" # Start buffering code
        else:
            # Not in a code block and not starting one, just print the line
            # (Optionally, add basic inline Markdown handling here)
            print(line, end='', flush=True)

# --- Main Loop ---
if __name__ == "__main__":
    try:
        # Read from stdin line by line
        for line in sys.stdin:
            process_line(line)

        # If the stream ends while still in a code block, print the remaining buffer
        if in_code_block:
             print("\n(Warning: Input ended inside a code block)", file=sys.stderr)
             print(code_buffer, end='', flush=True)

    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        sys.exit(0)
    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        sys.exit(1)
