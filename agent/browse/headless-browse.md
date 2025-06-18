headless-browse.js – Quick Reference
------------------------------------

Purpose
• Scrape a page’s DOM (starting at `document.body`) and convert it into a **clean, lightweight tree** of meaningful nodes, each with a stable short ID.  
• Provide three globally-accessible helpers:
  – `window.llmPack()`         → build / refresh the tree (`window.contentTree`)  
  – `window.llmDisplay()`      → show the tree as text in a fullscreen overlay  
  – `window.llmDisplayVisual()`→ draw red outlines around visible nodes in the tree  

Global artifacts
```
window.contentTree       // JSON-like structure of the page
window.formattedTree     // String version (tabs + newlines)
window.els[id]           // Map: generated id → DOM element
window.lastUsedConfigForTree
```

Main building blocks
1. `defaultConfig` – tunable options (skipped tags, visibility threshold, URL crop length, etc.)
2. `processElementNode(el, cfg)`  
   • Recursively walks the DOM, filtering SCRIPT/STYLE/etc., estimating *visibilityScore*, gathering attributes.  
   • Marks “meaningful” elements (inputs, links, media, etc.) and collapses single-child “wrapper” divs/sections.  
   • Returns a compact node object or `null` (pruned).  
3. `generateUniqueId(set, len)` – short a-z0-9 IDs, length grows to fit node count.
4. `extractPageContentTree(cfg, elemToIdMap)`  
   • Builds tree via `processElementNode`.  
   • Re-uses IDs from previous run (via `elemToIdMap`), assigns new ones, returns root node.  
5. Formatting utilities  
   • `formatNodeRecursive` → stringify one node.  
   • `formatTreeToString`  → wrap `formatNodeRecursive` for the whole tree.  
6. UI helpers  
   • `displayTreeOverlay(str)` – monospaced overlay + close button.  
   • `llmDisplayVisual` – red outlines + optional close button.
7. `llmPack(userCfg)`  
   • Wait for `window.load` + DOM “settle” period (MutationObserver, `settleTime`, `maxWaitTime`).  
   • Calls `extractPageContentTree`, stores globals, logs token count.

Usage pattern
```
await llmPack();          // or llmPack({instant:true})
llmDisplay();             // textual overlay
llmDisplayVisual(true);   // visual outlines + close button
```

Customization
Pass overrides to `llmPack` / `llmPack({showVisibility:true, visibilityThreshold:0.2})`, etc.

Notes
• The whole script is wrapped in an IIFE and only installs itself once (`if(window.llmPack)return`).  
• Designed to run in browser context (but guards for non-DOM environments).