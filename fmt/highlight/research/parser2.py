# Import necessary libraries
import sys
import re
import signal

# Attempt to import Pygments for syntax highlighting
try:
    from pygments import highlight
    from pygments.lexers import get_lexer_by_name, guess_lexer

    # from pygments.formatters import TerminalTrueColorFormatter
    # from pygments.formatters import TerminalFormatter
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
except ImportError:
    # Pygments is mandatory for this script version
    print(
        "Error: The 'pygments' library is required for syntax highlighting.",
        file=sys.stderr,
    )
    print("Please install it, for example using: pip install Pygments", file=sys.stderr)
    sys.exit(1)


# --- Custom ANSI Style for Pygments ---
class MyAnsiStyle(Style):
    """
    Custom Pygments style using ANSI color names to respect terminal themes.
    Maps token types to 'ansicolor' names.
    """

    background_color = None  # Use terminal's background
    background_color = "ansired"  # Use terminal's background
    default_style = ""  # Use terminal's default foreground

    styles = {
        Whitespace: "bg:ansiblack",  # No specific style for whitespace
        Comment: "bg:ansiblack ansibrightblack italic",
        Keyword: "bg:ansiblack ansiblue bold",
        Keyword.Constant: "bg:ansiblack ansicyan",
        Keyword.Declaration: "bg:ansiblack ansibrightblue",
        Keyword.Namespace: "bg:ansiblack ansimagenta bold",
        Keyword.Pseudo: "bg:ansiblack ansibrightblack",
        Keyword.Reserved: "bg:ansiblack ansiblue",
        Keyword.Type: "bg:ansiblack ansibrightred",
        Name: "bg:ansiblack ",  # Default
        Name.Attribute: "bg:ansiblack ansibrightyellow",
        Name.Builtin: "bg:ansiblack ansicyan",
        Name.Builtin.Pseudo: "bg:ansiblack ansibrightblack",
        Name.Class: "bg:ansiblack ansibrightgreen bold",
        Name.Constant: "bg:ansiblack ansired",
        Name.Decorator: "bg:ansiblack ansibrightmagenta",
        Name.Entity: "bg:ansiblack ansibrightyellow",
        Name.Exception: "bg:ansiblack ansibrightred bold",
        Name.Function: "bg:ansiblack ansigreen",
        Name.Function.Magic: "bg:ansiblack ansibrightgreen",
        Name.Label: "bg:ansiblack ansibrightyellow",
        Name.Namespace: "bg:ansiblack ansimagenta",
        Name.Other: "bg:ansiblack ",  # Default
        Name.Tag: "bg:ansiblack ansiblue bold",
        Name.Variable: "bg:ansiblack ansired",
        Name.Variable.Class: "bg:ansiblack ansibrightgreen",
        Name.Variable.Global: "bg:ansiblack ansibrightred",
        Name.Variable.Instance: "bg:ansiblack ansired",
        Name.Variable.Magic: "bg:ansiblack ansibrightgreen",
        String: "bg:ansiblack ansiyellow",
        String.Affix: "bg:ansiblack ansibrightblue",
        String.Backtick: "bg:ansiblack ansibrightred",
        String.Char: "bg:ansiblack ansiyellow",
        String.Delimiter: "bg:ansiblack ansibrightblue",
        String.Doc: "bg:ansiblack ansibrightblack italic",
        String.Double: "bg:ansiblack ansiyellow",
        String.Escape: "bg:ansiblack ansibrightred bold",
        String.Heredoc: "bg:ansiblack ansiyellow italic",
        String.Interpol: "bg:ansiblack ansimagenta",
        String.Other: "bg:ansiblack ansiyellow",
        String.Regex: "bg:ansiblack ansimagenta",
        String.Single: "bg:ansiblack ansiyellow",
        String.Symbol: "bg:ansiblack ansired bold",
        Number: "bg:ansiblack ansicyan",
        Number.Bin: "bg:ansiblack ansicyan",
        Number.Float: "bg:ansiblack ansibrightcyan",
        Number.Hex: "bg:ansiblack ansicyan",
        Number.Integer: "bg:ansiblack ansicyan",
        Number.Integer.Long: "bg:ansiblack ansicyan",
        Number.Oct: "bg:ansiblack ansicyan",
        Operator: "bg:ansiblack ansibrightmagenta",
        Operator.Word: "bg:ansiblack ansimagenta bold",
        Generic.Deleted: "bg:ansiblack ansired",
        Generic.Emph: "bg:ansiblack italic",
        Generic.Error: "ansibrightred bg:ansired",
        Generic.Heading: "bg:ansiblack bold ansiblue",
        Generic.Inserted: "bg:ansiblack ansigreen",
        Generic.Output: "bg:ansiblack ansibrightblack",
        Generic.Prompt: "bg:ansiblack ansiblue bold",
        Generic.Strong: "bg:ansiblack bold",
        Generic.Subheading: "bg:ansiblack bold ansimagenta",
        Generic.Traceback: "bg:ansiblack ansibrightred bold",
        Generic.Underline: "bg:ansiblack underline",
        Error: "ansibrightred bold bg:ansired",  # Ensure errors are visible
        Token.Other: "bg:ansiblack",  # Default for anything else
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
# Initialize the formatter once, globally
# formatter = TerminalFormatter(style=MyAnsiStyle, bg="dark")
# formatter = TerminalFormatter(bg="light")
# formatter = TerminalFormatter(style=MyAnsiStyle)
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
    global in_code_block, code_language, code_buffer, formatter

    # --- Fenced Code Blocks ---
    code_block_match = re.match(r"^\s*```\s*(\w*)\s*$", line)

    if code_block_match:
        if in_code_block:
            # End of code block
            in_code_block = False
            if code_buffer:  # Only process if there's code in the buffer
                try:
                    # Use specified lexer or guess
                    if code_language:
                        lexer = get_lexer_by_name(code_language)
                    else:
                        lexer = guess_lexer(code_buffer)
                    # Highlight the whole buffer using the global formatter
                    highlighted_code = highlight(code_buffer, lexer, formatter)
                    # Add background color line by line
                    highlighted_lines = [
                        f"{CODE_BG}{l}{RESET}"
                        for l in highlighted_code.rstrip("\n").split("\n")
                    ]
                    print("\n".join(highlighted_lines))
                except ClassNotFound:
                    # Fallback if lexer not found - print raw code
                    print(
                        f"{CODE_BG}# Lexer '{code_language or '(guessed)'}' not found. Printing raw code.{RESET}"
                    )
                    print(f"{CODE_BG}{code_buffer.rstrip()}{RESET}")
                except Exception as e:
                    # Fallback for any other highlighting error - print raw code
                    print(f"{CODE_BG}# Error during highlighting: {e}{RESET}")
                    print(f"{CODE_BG}{code_buffer.rstrip()}{RESET}")

            code_buffer = ""  # Reset buffer
            code_language = None
            # formatter = None # No need to reset the global formatter
            return  # Don't print the closing ``` line itself
        else:
            # Start of code block
            in_code_block = True
            code_language = code_block_match.group(1) or None
            code_buffer = ""  # Clear buffer for new block
            # No need to initialize formatter here, it's global
            return  # Don't print the opening ``` line itself

    if in_code_block:
        code_buffer += line  # Accumulate lines within the code block
        return  # Don't process/print lines inside block until it's closed

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
        # If the input ends while still in a code block, attempt to highlight and print what we have
        if in_code_block and code_buffer:
            print(
                f"\n{CODE_BG}--- Code block potentially truncated ---{RESET}",
                file=sys.stderr,
            )
            try:
                # Attempt to get the lexer
                if code_language:
                    lexer = get_lexer_by_name(code_language)
                else:
                    lexer = guess_lexer(code_buffer)
                # Highlight and print using the global formatter
                highlighted_code = highlight(code_buffer, lexer, formatter)
                highlighted_lines = [
                    f"{CODE_BG}{l}{RESET}"
                    for l in highlighted_code.rstrip("\n").split("\n")
                ]
                print("\n".join(highlighted_lines))
            except ClassNotFound:
                # Fallback if lexer not found for truncated block
                print(
                    f"{CODE_BG}# Lexer '{code_language or '(guessed)'}' not found for truncated block. Printing raw code.{RESET}"
                )
                print(f"{CODE_BG}{code_buffer.rstrip()}{RESET}")
            except Exception as e:
                # Fallback for any other highlighting error in truncated block
                print(f"{CODE_BG}# Error highlighting truncated block: {e}{RESET}")
                print(
                    f"{CODE_BG}{code_buffer.rstrip()}{RESET}"
                )  # Print raw code as fallback

    except BrokenPipeError:
        # Handle cases where the reading pipe is closed (e.g., piping to `head`)
        sys.stderr.close()  # Suppress further stderr errors
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
