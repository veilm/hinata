#!/usr/bin/env python3
import sys
import time

# Print some content that will stay visible
print("=== This content stays visible ===")
print("Just like with fzf!")
print()

# Reserve 5 lines for our TUI
HEIGHT = 5

# Save cursor position and create empty space
sys.stdout.write("\033[s")  # Save cursor
for _ in range(HEIGHT):
    print()
sys.stdout.write(f"\033[{HEIGHT}A")  # Move back up
sys.stdout.flush()

# Simple animation loop
try:
    counter = 0
    while True:
        # For each line in our reserved area
        for line in range(HEIGHT):
            # Save position, move to line, clear it, write content
            sys.stdout.write("\033[s")  # Save
            if line > 0:
                sys.stdout.write(f"\033[{line}B")  # Move down
            sys.stdout.write("\033[2K\r")  # Clear line

            # Different content for each line
            if line == 0:
                sys.stdout.write(f"┌─── Frame: {counter:04d} ───┐")
            elif line == 1:
                sys.stdout.write(f"│ Time: {time.strftime('%H:%M:%S')}     │")
            elif line == 2:
                progress = "█" * (counter % 20) + "░" * (20 - counter % 20)
                sys.stdout.write(f"│ {progress} │")
            elif line == 3:
                sys.stdout.write(f"│ Ctrl+C to exit      │")
            elif line == 4:
                sys.stdout.write(f"└─────────────────────┘")

            sys.stdout.write("\033[u")  # Restore position

        sys.stdout.flush()
        counter += 1
        time.sleep(0.1)

except KeyboardInterrupt:
    # Move to end of our reserved area before exiting
    sys.stdout.write(f"\033[{HEIGHT}B")
    sys.stdout.flush()
    print("\nExited cleanly!")
