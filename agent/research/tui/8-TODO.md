# TODO: Discrepancies between 8.c and tmux's input.c parser

This document lists the features from `tmux`'s terminal input parser that are missing in `8.c`. They are ordered by priority for implementation.

## Priority 1: Critical for Basic Neovim Functionality

3.  **Alternate Screen Buffer (CSI ?1049h / ?1049l)**
    - **What:** `8.c` doesn't handle the private mode sequences for switching to and from the alternate screen buffer.
    - **Why:** Full-screen applications use this to get a clean screen to draw on, and restore the original screen content on exit. Without it, the application's UI will be drawn over the shell prompt and remain there after exit.
    - **Implementation:** Implement a secondary grid and switch between them.
    - **Ref:** `tmux/input.c:input_csi_dispatch_sm_private` / `rm_private`

## Priority 2: Important for Correctness and Advanced UI

4.  **Device Status Report (DSR - CSI n)**
    - **What:** `8.c` doesn't respond to status report requests.
    - **Why:** `CSI 6 n` (Report Cursor Position) is frequently used by applications to query the cursor's location. Failing to respond can cause applications to hang or mis-render.
    - **Implementation:** When `CSI 6 n` is received, write `ESC[<row>;<col>R` back to the master PTY.
    - **Ref:** `tmux/input.c:input_csi_dispatch` (case `INPUT_CSI_DSR`)

## Priority 3: Nice-to-have and Compatibility Features

8.  **Character Sets (SCS)**
    - **What:** No support for `ESC ( B` (ASCII) or `ESC ( 0` (DEC Special Graphics).
    - **Why:** The special graphics set is used for drawing lines and boxes in TUIs. Without it, borders and other UI elements will be rendered as incorrect characters (e.g., `lqqqk` instead of `┌───┐`).
    - **Implementation:** Add state to track G0/G1 charsets and map input characters to the DEC Special Graphics set when active.
    - **Ref:** `tmux/input.c:input_esc_dispatch`

9.  **OSC (Operating System Command) Parsing**
    - **What:** `8.c` consumes OSC sequences but doesn't parse the content.
    - **Why:** OSC is used for many features, most commonly setting the window title (`OSC 2;...`).
    - **Implementation:** Parse `OSC 2;<title>ST` and store the title.
    - **Ref:** `tmux/input.c:input_exit_osc`

10. **Mouse Support**
    - **What:** No handling of mouse mode setting sequences (`?1000h`, etc.).
    - **Why:** Not essential for `nvim`'s core function but required for mouse interaction.
    - **Implementation:** Consume mouse-related private mode sequences. Forwarding mouse events from the host terminal is a separate, larger task.
    - **Ref:** `tmux/input.c:input_csi_dispatch_sm_private`

11. **Robust Parameter Parsing**
    - **What:** `8.c` uses `sscanf`, which can be fragile.
    - **Why:** A more robust parser will handle empty parameters (e.g., `CSI ;5H`) and other edge cases correctly. `tmux`'s `input_split` is a good model.
    - **Implementation:** Replace `sscanf` with a loop that splits parameters on `;`.

12. **DCS (Device Control String) and other sequence types**
    - **What:** `8.c` has a minimal consumer for DCS. `tmux` handles passthrough and specific sequences like SIXEL.
    - **Why:** This is for advanced/exotic terminal features.
    - **Implementation:** Low priority, current consumer is probably fine for now.
