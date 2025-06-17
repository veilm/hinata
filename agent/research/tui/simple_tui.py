#!/usr/bin/env python3
import sys
import time
import random
import signal

class SimpleTUI:
    def __init__(self, height=10):
        self.height = height
        self.running = True
        
        # Save cursor position
        sys.stdout.write('\033[s')
        
        # Reserve space by printing empty lines
        for _ in range(height):
            print()
        
        # Move cursor back up
        sys.stdout.write(f'\033[{height}A')
        sys.stdout.flush()
        
        # Setup signal handler for clean exit
        signal.signal(signal.SIGINT, self.cleanup)
        
    def cleanup(self, signum=None, frame=None):
        """Clean up and restore terminal"""
        self.running = False
        # Move cursor to the end of our reserved area
        sys.stdout.write(f'\033[{self.height}B')
        sys.stdout.flush()
        sys.exit(0)
    
    def update_line(self, line_num, content):
        """Update a specific line in our reserved area"""
        # Save cursor position
        sys.stdout.write('\033[s')
        
        # Move to the line we want to update (relative to our start)
        if line_num > 0:
            sys.stdout.write(f'\033[{line_num}B')
        
        # Clear the line and write content
        sys.stdout.write('\033[2K\r' + content)
        
        # Restore cursor position
        sys.stdout.write('\033[u')
        sys.stdout.flush()
    
    def run_animation(self):
        """Run a simple animation in our reserved space"""
        frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        colors = ['\033[31m', '\033[32m', '\033[33m', '\033[34m', '\033[35m', '\033[36m']
        
        frame_idx = 0
        counter = 0
        
        while self.running:
            # Update different lines with different content
            self.update_line(0, f"╔════════════════════════════════════════╗")
            self.update_line(1, f"║ Simple TUI Demo - Frame: {counter:04d}      ║")
            self.update_line(2, f"╠════════════════════════════════════════╣")
            
            # Animated spinner
            spinner = frames[frame_idx % len(frames)]
            self.update_line(3, f"║ Loading {spinner} {spinner} {spinner}                        ║")
            
            # Progress bar
            progress = (counter % 100) / 100
            bar_width = 30
            filled = int(bar_width * progress)
            bar = '█' * filled + '░' * (bar_width - filled)
            self.update_line(4, f"║ [{bar}] {int(progress*100):3d}% ║")
            
            # Random colored dots
            dots = []
            for i in range(5):
                color = random.choice(colors)
                dot = random.choice(['●', '○', '◐', '◑', '◒', '◓'])
                dots.append(f"{color}{dot}\033[0m")
            self.update_line(5, f"║ Animation: {' '.join(dots)}          ║")
            
            # Time display
            current_time = time.strftime("%H:%M:%S")
            self.update_line(6, f"║ Time: {current_time}                     ║")
            
            # Wave animation
            wave_chars = ['~', '≈', '≋', '～', '〜']
            wave_offset = counter % len(wave_chars)
            wave = ''.join([wave_chars[(i + wave_offset) % len(wave_chars)] for i in range(20)])
            self.update_line(7, f"║ {wave}             ║")
            
            self.update_line(8, f"║ Press Ctrl+C to exit                   ║")
            self.update_line(9, f"╚════════════════════════════════════════╝")
            
            frame_idx += 1
            counter += 1
            time.sleep(0.1)

def main():
    # Print some content before our TUI to show it doesn't clear the screen
    print("=== Previous terminal content ===")
    print("This content will remain visible above the TUI")
    print("Just like with fzf!")
    print("=" * 40)
    print()
    
    # Create and run our TUI
    tui = SimpleTUI(height=10)
    try:
        tui.run_animation()
    except KeyboardInterrupt:
        tui.cleanup()

if __name__ == "__main__":
    main()
