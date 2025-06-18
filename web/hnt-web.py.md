# hnt-web.py – Quick Structural Overview
(See hnt-web.py for full code)

Purpose  
• Exposes a REST/streaming API and static web UI for the `hnt-chat` CLI conversation system.  
• Wraps FastAPI around the on-disk “conversation” folder model used by `hnt-chat`.  
• Delegates heavy LLM work to the CLI; acts mainly as HTTP glue plus static hosting.

Key Constants  
• DEFAULT_MODEL_NAME – fallback LLM model reference.  

Utility Helpers  
• get_web_data_dir() – locate `$XDG_DATA_HOME`/hinata/web (or `~/.local/share/...`).  
• get_conversations_dir() – ensure & return `$XDG_DATA_HOME`/hinata/chat/conversations.  

FastAPI App  
app = FastAPI()

Static File Mounts (executed at import time)  
• /css → …/web/css  
• /js  → …/web/js  
• “/”             → index.html  
• /conversation-page/{path} → conversation.html  

Conversation APIs  
GET  /api/conversations  
    → list {id, title, is_pinned} (sorted pinned-first, newest-first)

GET  /api/conversation/{id}  
    → full conversation ({messages, other_files, title, model, is_pinned})

PUT  /api/conversation/{id}/title        – change title.txt (empty → “-”)  
PUT  /api/conversation/{id}/model        – update model.txt (empty → default)  
POST /api/conversations/create           – call `hnt-chat new`, return new id  
POST /api/conversation/{id}/add-message  – call `hnt-chat add` with body content  
POST /api/conversation/{id}/gen-assistant  
     – stream `hnt-chat gen --merge --separate-reasoning` stdout back to client

Message Maintenance  
POST /api/conversation/{id}/message/{file}/archive  
     – rename to `<ts>-archived-{file}`  
PUT  /api/conversation/{id}/message/{file}/edit  
     – copy → archive, then overwrite with new content

Conversation Maintenance  
POST /api/conversation/{id}/fork  
     – create new conv via `hnt-chat new`, copy all files, bump title suffix.  
POST /api/conversation/{id}/pin-toggle  
     – toggles presence of pinned.txt

Error Handling Highlights  
• Uses HTTPException with relevant HTTP codes.  
• Validates roles & model strings, sanitises empty inputs.  
• Streams stderr for long-running generation.  
• Verifies presence of `hnt-chat` binary (shutil.which) before streaming.

__main__ Guard  
If run directly: `uvicorn.run(app, host="0.0.0.0", port=2027)`

File Layout Cheat-sheet  
hiniata data dirs  
└─ $XDG_DATA_HOME or ~/.local/share  
   └─ hinata  
      ├─ web/            (static assets built by separate script)  
      └─ chat/  
         └─ conversations/  
            └─ <conversation_id>/  
               ├─ title.txt  
               ├─ model.txt  
               ├─ pinned.txt   (optional)  
               ├─ <n>-<role>.md  
               └─ other attachments…

Typical Developer Touch-points  
• Add new API route → define @app.<method>(…) before static mounts.  
• Modify conversation disk format → update filename_pattern & helpers.  
• Change port / host → bottom `uvicorn.run`.  