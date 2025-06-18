# conversation.html – Quick Structural & Functional Reference

Purpose  
Displays a single chat‐style “conversation” page, letting users read messages, edit metadata (title/model), and perform high-level actions (fork, pin/unpin, jump to latest).

Top-level layout  
• `<head>` – metadata, favicon (emoji SVG), Google Fonts, global stylesheet link (`/css/style.css`).  
• `<body>` – one main `.container` div wrapping:

  1. Back nav: `<a>` (`.back-link`) → returns to conversations list.  
  2. **Title section** (`.title-section`)  
     • `<h1 id="conversation-id-display">` – placeholder; JS swaps in conversation title/ID.  
     • Editable fields:  
       – `#conversation-title-input` (Title)  
       – `#conversation-model-input` (Model)  
     • **Page-action buttons** (`.page-actions-group`)  
       – `#fork-conversation-btn` – clones the conversation.  
       – `#pin-toggle-btn` – toggles pin state; label text set by JS (“Pin” / “Unpin”).  
       – `#jump-to-latest-btn` – scrolls to newest message.  
  3. **Dynamic content placeholders**  
     • `#messages-container` – all chat messages injected by JS.  
     • `#other-files-container` – auxiliary files attached to conversation.

Script & styling hooks  
• `/js/script.js` (deferred) handles:  
  – Fetching conversation data, rendering messages/files.  
  – Updating `<title>` element and `#conversation-id-display`.  
  – Wiring up button handlers + pin logic.  
• CSS classes/IDs referenced above match rules in `/css/style.css`.

Key takeaways for developers  
• The HTML is mostly static “skeleton”; all runtime data population and interactivity happen in `script.js`.  
• Maintain unique IDs/classes as JS relies on them for DOM queries.  
• When adding new actions or UI sections, keep them inside `.container` for styling consistency and wire them via `script.js`.  
• Minimal SEO/SSR concerns—this page is JS-driven and works after full client load.