# Hinata Web Static – Developer High-Level Reference  
*(directory: `/src/hinata/web/static`)*

What lives here  
----------------
A **fully client-side bundle** (HTML + CSS + JavaScript) for the Hinata Chat
web-app.  Everything under this folder is shipped verbatim by the server as
“static assets”; once they reach the browser, `script.js` talks to the REST
backend (`/api/...`) to fetch / mutate data.

Quick mental model  
------------------
1. The browser downloads two **HTML skeletons**: the *conversation list* page
   (`index.html`) and the *single conversation* page (`conversation.html`).
2. Both reference the shared **dark-theme stylesheet** (`css/style.css`).
3. Each page defers to a **single page-controller** (`js/script.js`) that:
   • inspects `window.location.pathname`  
   • fetches the necessary JSON from the backend  
   • generates / updates DOM nodes, wires all buttons & textareas.
4. External tooling:  
   • Fonts are pulled from Google Fonts.  
   • All data interaction is via the server-side REST API documented inside
     `js/script.md`.

Where to dive deeper  
--------------------
Need details on… | Open this doc first
-----------------|---------------------------------
Overall JS flow / helpers | `js/script.md`
Conversation list markup | `index.md`
Conversation detail markup | `conversation.md`
Design tokens & CSS class names | `css/style.md`
REST endpoints used | `js/script.md` (API section)

How the pieces fit together  
---------------------------
```
index.html  ──┐              conversation.html ──┐
              │                                 │
              │ imports                          │ imports
css/style.css ─┴────────────┐     css/style.css ─┴────────────┐
                            │                                 │
                      js/script.js  (runs on both pages) <─────┘
                            │
                            └── calls `/api/...` endpoints
```

Development tips  
----------------
• **Add a new UI element?**  
  – Put the static placeholder in the right HTML skeleton.  
  – Style it in `css/style.css` (use existing utility classes where possible).  
  – Attach behaviour inside the relevant function in `script.js`.

• **Extending message types / colours?**  
  – Add a `.message-<type>` block to the CSS and map it in JS render helpers.

• **Avoid coupling**: JS selects nodes via the IDs/classes defined in the docs
  above—rename with care.

That’s it—four small files, one clear flow.  Skim the table above to jump into
finer detail whenever necessary.