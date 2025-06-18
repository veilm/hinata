# script.js – Quick Reference

Single-page front-end controller for the conversation web-app.  
Loads either the *conversation list* ( `/` ) or an individual *conversation detail
page* ( `/conversation-page/:id` ) and wires all user interactions to the REST
API.

---

## Top-Level Flow

1. `DOMContentLoaded` → inspect `window.location.pathname`
   • `/`               → `loadConversationsList()`
   • `/conversation-page/:id` → `loadConversationDetails(id)`

All other logic is reached from one of these two entry points.

---

## Major Responsibilities & Key Helpers

| Area | Function(s) | Notes |
|------|-------------|-------|
| Basic utils | `escapeHtml`, `clearErrorMessages`, `handleError` | XSS safety and lightweight error banners. |
| Conversation list (root page) | `loadConversationsList`, `handleCreateConversation` | Renders `<ul>`, pin emoji, create button. |
| Conversation detail page | `loadConversationDetails` | Fetches metadata, messages, files. Installs all per-page listeners. |
| Message composer | `setupMessageInputArea`, `handleAddMessage`, `handleGenAssistant` | Fixed textarea with auto-resize, four action buttons (Add User / System / Assistant, Gen Assistant). |
| Message item actions | `toggleEditState`, `handleSaveMessage`, `handleArchiveMessage` | Edit inline with autosizing `<textarea>`, archive, SVG icon buttons. |
| Conversation attrs | `updateConversationTitle`, `updateConversationModel`, `handlePinToggle`, `handleForkConversation` | PUT/POST calls that immediately patch UI. |
| Misc UX | `jumpToLatestMessage`, `updateGlobalActionButtonsState`, SVG icon constants | Smooth scroll to newest message and global-button enable/disable. |

---

## API Endpoints (all relative to `/api`)

- `GET  /conversations`
- `POST /conversations/create`
- `GET  /conversation/:id`
- `PUT  /conversation/:id/title`
- `PUT  /conversation/:id/model`
- `POST /conversation/:id/pin-toggle`
- `POST /conversation/:id/fork`
- `POST /conversation/:id/add-message`
- `POST /conversation/:id/gen-assistant` (SSE/stream)
- `PUT  /conversation/:id/message/:filename/edit`
- `POST /conversation/:id/message/:filename/archive`

---

## Component/DOM Cheatsheet

```
#conversation-list-container   (list page)

#conversation-id-display       (detail header)
#conversation-title-input      (inline editable <input>)
#conversation-model-input
#pin-toggle-btn
#fork-conversation-btn
#jump-to-latest-btn

#messages-container            (holds .message items)
.message
  .message-header
  .message-content-wrapper
  .message-actions             (SVG icon buttons)

#other-files-container         (detail page, non-message files)

#message-input-area            (fixed footer)
  <textarea id="new-message-content">
  #message-buttons
```

---

## Notes & Gotchas

- All buttons are cloned before (re)attaching listeners to avoid duplicate handlers on page reload.
- Textareas auto-expand up to 8 lines; beyond that they become scrollable.
- Editing a message sets `data-editing="true"` on `.message`; this disables global composer buttons.
- The *assistant generation* endpoint streams; interim text is shown in a placeholder message until the reload in `finally`.