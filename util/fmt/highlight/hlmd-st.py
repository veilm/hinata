#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pygments>=2.19.1"]
# ///

# Import necessary libraries
import sys
import re
import signal

# Attempt to import Pygments for syntax highlighting
from pygments import highlight
from pygments.lexers import get_lexer_by_name

# from pygments.formatters import TerminalTrueColorFormatter
from pygments.formatters import TerminalFormatter

from pygments.formatters import Terminal256Formatter
from pygments.util import ClassNotFound
from pygments.style import Style
from pygments.token import (
    Keyword,
    Name,
    Comment,
    String,
    Error,
    Number,
    Operator,
    Generic,
    Token,
    Whitespace,
)  # Import Style and Tokens


# --- Custom ANSI Style for Pygments ---
class MyAnsiStyle(Style):
    """
    Custom Pygments style using ANSI color names to respect terminal themes.
    Maps token types to 'ansicolor' names.
    """

    default_style = ""  # Use terminal's default foreground

    styles = {
        Whitespace: "",
        Comment: "ansibrightblack",  # Subtle comments, no italic for cleaner look
        Keyword: "ansibrightmagenta",  # Bolder, more vibrant keywords
        Keyword.Constant: "ansibrightcyan",
        Keyword.Declaration: "ansimagenta",
        Keyword.Namespace: "ansibrightblue bold",
        Keyword.Pseudo: "ansibrightblack",
        Keyword.Reserved: "ansimagenta",
        Keyword.Type: "ansicyan",
        Name: "",
        Name.Attribute: "ansiyellow",
        Name.Builtin: "ansibrightblue",
        Name.Builtin.Pseudo: "ansiblue",
        Name.Class: "ansibrightgreen",  # Bold removed for consistency
        Name.Constant: "ansibrightred",
        Name.Decorator: "ansibrightmagenta",
        Name.Entity: "ansiyellow",
        Name.Exception: "ansibrightred",  # Bold removed for less visual noise
        Name.Function: "ansibrightgreen",
        Name.Function.Magic: "ansigreen bold",
        Name.Label: "ansiyellow",
        Name.Namespace: "ansibrightblue",
        Name.Other: "",
        Name.Tag: "ansimagenta",
        Name.Variable: "ansicyan",  # Changed to cyan for better variable visibility
        Name.Variable.Class: "ansibrightcyan",
        Name.Variable.Global: "ansibrightcyan bold",
        Name.Variable.Instance: "ansicyan",
        Name.Variable.Magic: "ansibrightcyan bold",
        String: "ansibrightgreen",  # Brighter strings for better distinction
        String.Affix: "ansigreen",
        String.Backtick: "ansibrightgreen bold",
        String.Char: "ansigreen",
        String.Delimiter: "ansigreen",
        String.Doc: "ansibrightblack",  # No italic for doc strings
        String.Double: "ansibrightgreen",
        String.Escape: "ansiyellow bold",
        String.Heredoc: "ansigreen",
        String.Interpol: "ansiyellow",
        String.Other: "ansibrightgreen",
        String.Regex: "ansiyellow",
        String.Single: "ansibrightgreen",
        String.Symbol: "ansiyellow bold",
        Number: "ansibrightred",  # Bright red for numbers to stand out
        Number.Bin: "ansibrightred",
        Number.Float: "ansired",
        Number.Hex: "ansibrightred",
        Number.Integer: "ansibrightred",
        Number.Integer.Long: "ansired",
        Number.Oct: "ansibrightred",
        Operator: "ansiwhite bold",  # Bold white for operators to stand out
        Operator.Word: "ansiwhite bold",
        Generic.Deleted: "ansired",
        Generic.Emph: "italic",
        Generic.Error: "ansiwhite bg:ansired",
        Generic.Heading: "ansibrightblue bold",
        Generic.Inserted: "ansibrightgreen",
        Generic.Output: "ansibrightblack",
        Generic.Prompt: "ansibrightblue",
        Generic.Strong: "bold",
        Generic.Subheading: "ansiblue bold",
        Generic.Traceback: "ansibrightred",
        Generic.Underline: "underline",
        Error: "ansiwhite bold bg:ansired",
        Token.Other: "",
    }


# --- ANSI Escape Codes (for non-Pygments parts) ---
RESET = "\033[0m"
BOLD = "\033[1m"
ITALIC = "\033[3m"
# Basic colors (you can customize these)
HEADER_COLOR = "\033[94m"  # Blue
BOLD_COLOR = "\033[93m"  # Yellow
ITALIC_COLOR = "\033[92m"  # Green
CODE_COLOR = "\033[95m"  # Magenta
CODE_BG = "\033[48;5;235m"  # Dark grey background for code blocks

# --- State ---
in_code_block = False
code_language = None
code_buffer = ""
code_gen_pos = 0  # Tracks the length of the already emitted highlighted code
lexer = None
# Initialize the formatter once, globally
# formatter = TerminalFormatter(style=MyAnsiStyle, bg="dark")
# formatter = TerminalFormatter(bg="light")
# formatter = TerminalFormatter(style=MyAnsiStyle)

# formatter = Terminal256Formatter(style="monokai")
formatter = Terminal256Formatter(style=MyAnsiStyle)


def apply_inline_styles(line):
    """Applies bold, italic, and inline code styles using regex."""
    # Bold (**text** or __text__)
    line = re.sub(r"\*\*(.*?)\*\*", rf"{BOLD}{BOLD_COLOR}\1{RESET}", line)
    line = re.sub(r"__(.*?)__", rf"{BOLD}{BOLD_COLOR}\1{RESET}", line)
    # Italic (*text* or _text_) - Careful not to mess up bold
    line = re.sub(
        r"(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)",
        rf"{ITALIC}{ITALIC_COLOR}\1{RESET}",
        line,
    )
    # Avoid matching underscores within words for italics
    line = re.sub(
        r"(?<!\w)_(?!_)(.*?)(?<!\w)_(?!\w)", rf"{ITALIC}{ITALIC_COLOR}\1{RESET}", line
    )
    # Inline code (`code`)
    line = re.sub(r"`(.*?)`", rf"{CODE_COLOR}\1{RESET}", line)
    return line


def process_line(line):
    """Processes a single line of Markdown input."""
    global in_code_block, code_language, code_buffer, code_gen_pos, formatter, lexer

    # --- Fenced Code Blocks ---
    code_block_match = re.match(r"^\s*```\s*(\w*)\s*$", line)

    if code_block_match:
        if in_code_block:
            # End of code block
            in_code_block = False
            lexer = None  # Reset lexer
            code_buffer = ""  # Reset buffer
            code_language = None
            code_gen_pos = 0  # Reset position tracker
            print(RESET, end="")  # Ensure styles are reset after code block
            return  # Don't print the closing ``` line itself
        else:
            # Start of code block
            in_code_block = True
            code_language = code_block_match.group(1) or None
            code_buffer = ""  # Clear buffer for new block
            code_gen_pos = 0  # Reset position tracker
            lexer = None  # Reset lexer, will be determined on first line of code
            # print(CODE_BG, end="") # Optional: Start with a background color immediately
            return  # Don't print the opening ``` line itself

    if in_code_block:
        # Determine lexer on the first line inside the block
        if lexer is None and code_language:
            try:
                lexer = get_lexer_by_name(code_language)
            except ClassNotFound:
                # Use a default or plain text lexer if specified one not found
                try:
                    lexer = get_lexer_by_name("text")  # Fallback lexer
                except ClassNotFound:  # Should not happen for 'text'
                    print(f"# Fallback lexer 'text' not found.", file=sys.stderr)
                    # If even text lexer fails, we cannot highlight
                    print(line.rstrip())  # Print raw line
                    return

        elif lexer is None:  # No language specified
            try:
                lexer = get_lexer_by_name("text")  # Default to plain text
            except ClassNotFound:
                print(f"# Default lexer 'text' not found.", file=sys.stderr)
                print(line.rstrip())  # Print raw line
                return

        # Accumulate line, highlight the whole buffer, extract and print the new part
        code_buffer += line
        try:
            # Highlight the cumulative buffer
            full_highlighted_output = highlight(code_buffer, lexer, formatter)

            # Extract the newly highlighted portion
            # This assumes the formatter doesn't drastically change the length of already processed parts
            # (which is generally true for terminal formatters)
            new_highlighted_chunk = full_highlighted_output[code_gen_pos:]

            # Print the new chunk. The highlight function preserves newlines,
            # and end="" prevents print() from adding an extra one.
            print(new_highlighted_chunk, end="")

            # Update the position tracker
            # Store the length of the full highlighted output *including* any
            # newline added by the formatter at the end.
            code_gen_pos = len(full_highlighted_output)

        except Exception as e:
            # Fallback for any highlighting error - print raw line for this step
            print(
                f"# Error during incremental highlighting: {e}{RESET}", file=sys.stderr
            )
            print(line.rstrip(), end="")  # Print raw line content
            # Try to keep buffer consistent, but highlighting is likely broken now
            code_gen_pos += len(line)  # Rough estimate

        return  # Line processed within code block

    # --- Headers ---
    header_match = re.match(r"^(#+)\s+(.*)", line)
    if header_match:
        level = len(header_match.group(1))
        text = header_match.group(2)
        styled_text = apply_inline_styles(text)  # Apply styles within header
        print(f"{BOLD}{HEADER_COLOR}{'#' * level} {styled_text}{RESET}")
        return

    # --- Horizontal Rules ---
    hr_match = re.match(r"^[\s]*([-\*=_]){3,}[\s]*$", line)
    if hr_match:
        # Basic HR representation
        try:
            # Attempt to get terminal width for a full line
            import shutil

            width = shutil.get_terminal_size((80, 20)).columns
            print(f"{BOLD}{HEADER_COLOR}{'─' * width}{RESET}")
        except (ImportError, OSError):
            # Fallback if width cannot be determined
            print(f"{BOLD}{HEADER_COLOR}----------{RESET}")
        return

    # --- Regular Text ---
    # Apply inline styles to the rest of the line
    styled_line = apply_inline_styles(line.rstrip())
    print(styled_line)


def main():
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    # Set default encoding if possible (important for pipes)
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        # sys.stdin/stdout might not have reconfigure (e.g., in some environments)
        pass

    try:
        for line in sys.stdin:
            process_line(line)
        # Ensure style is reset if script ends abruptly or normally
        if in_code_block:
            print(RESET, end="")  # Reset style if we were in a code block
            print(f"\n--- Code block potentially truncated ---{RESET}", file=sys.stderr)
        # No need for the explicit end-of-stream highlighting block anymore,
        # as highlighting is done incrementally.

    except BrokenPipeError:
        # Handle cases where the reading pipe is closed (e.g., piping to `head`)
        print(RESET, end="")  # Ensure reset on broken pipe
        sys.stderr.close()  # Suppress further stderr errors
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
