# style.css – Quick Reference

Dark-theme stylesheet used across the Chat application.

Sections / Key Selectors
------------------------
1. **Global / Body**
   • Monospace font stack  
   • Mobile-first 0px padding, adaptive bottom padding for fixed input  
   • Media query (≥768 px) adds 20 px desktop padding

2. **Headings (h1, h2)**  
   • Light text, subtle bottom border

3. **Links** – Ice-blue color, underline on hover

4. **Layout Helpers**
   • `.container` – Inner page wrapper  
   • `.other-files-*`, `.page-actions-group` – Utility wrappers/dividers

5. **Conversation Messages**
   • `.message` – Base message box  
   • `.message-header` – flex header (role, timestamp)  
   • `.message-role`, `.message-filename` – typography helpers  
   • Type modifiers:  
     `.-system`, `.-user`, `.-assistant`, `.-assistant-reasoning`, `.-unknown`  
     (all add colored left bar + specific tweaks)

6. **Inline Message Actions**
   • `.message-actions` – Flex row with icon buttons (edit, archive, …)  
   • Color inherits from parent message type

7. **Conversation List (sidebar)**
   • `#conversation-list-container` styles list rows, title input, pin icon

8. **Top-Level Conversation Title/Input**
   • `#conversation-id-display`, `.title-edit-container`, `.model-edit-container`

9. **Create / Pin / Fork Buttons**
   • `.page-action-button` base + specific IDs (`#fork-conversation-btn`, etc.)

10. **Fixed Message Input Bar**
    • `#message-input-area` – fixed bottom bar  
    • `#new-message-content`, `#message-buttons` – textarea + action buttons

11. **Scrollable Elements & Custom Scrollbars**
    • WebKit scrollbar overrides and Firefox equivalents

Media Queries
-------------
• Only one breakpoint at 768 px adjusts body and input-bar horizontal positioning.

Design Tokens
-------------
Color scheme = dark gray backgrounds (#121212–#2c2c2c), light text (#e0e0e0), accent icy-blue (#6ec8ff).  
Borders are thin solid (#333/444). No border-radius (flat/minimal look).

Usage Tips
----------
• Add new message types by extending `.message-<type>` and updating `.message-actions` color overrides.  
• Keep fixed input bar height in sync with body `padding-bottom`.  
• All interactive buttons share transition on `background-color`.