#!/usr/bin/env python3
import sys, rich
from rich.console import Console
from rich.markdown import Markdown

console = Console()
buffer = []

for line in sys.stdin:
    buffer.append(line)
    # Re-parse the entire buffer each tick; fast enough for TTY speeds
    md = Markdown("".join(buffer), code_theme="monokai")
    console.clear()          # redraw in-place
    console.print(md, end="")
