# index.html – quick reference

Purpose: render the “Conversations” page of the Hinata Chat web app.

Main points
-----------

• HTML5 document (`<!DOCTYPE html>`) with `lang="en"`.  
• `<head>`
  - Character set UTF-8 & responsive viewport
  - Title: **Hinata Chat - Conversations**
  - In-page emoji favicon (❄️) via data-URI
  - Google Fonts: **Inter** & **Roboto Mono** (preconnect + stylesheet link)
  - External stylesheet: `/css/style.css`

• `<body>`
  - `.container` wrapper
    * `<h1>` page header: “Hinata Chat ❄️ - Conversations”
    * `.create-conversation-section` containing button `#create-conversation-btn`
    * `#conversation-list-container` placeholder that initially shows “Loading conversations…”  
      – will be filled dynamically

• Script  
  - `/js/script.js` loaded with `defer`; expected to:
    * fetch conversation data
    * populate `#conversation-list-container`
    * attach click handler to “Create New Conversation” button

The file is purely structural/presentational; all interactivity is delegated to the external JavaScript.