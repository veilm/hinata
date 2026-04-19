# hnt-web
`hnt-web`: a minimal web app wrapping `hnt-chat`

- features ❌
- budget ❌
- UX ❌
- active users ❌
- GitHub stars ❌
- X reposts ❌
- brain damage ✅ (minimalism™)

## install
```
# Go is the only dependency
curl hnt-agent.org/install | sh

# start the server (runs in the foreground)
hnt-web

# open http://127.0.0.1:2027/ in your browser
```

the architecture is vanilla Go (http std lib) + Vanilla JS. the entire server is
one executable (hnt-web). the frontend is copied to `$XDG_DATA_HOME` during the
installation and then hnt-web serves from there

=> you don't need any docker or npm, just Go

it uses hnt-chat as the LLM backend, so all of your messages are plaintext and
simple to manage externally

## screenshots, as of Nov 2025
![ss 0](https://sucralose.moe/static/hnt-web1-0.png)

![ss 1](https://sucralose.moe/static/hnt-web1-1.png)

![ss 2](https://sucralose.moe/static/hnt-web1-2.png)

![ss 3](https://sucralose.moe/static/hnt-web1-3.png)

![ss 4](https://sucralose.moe/static/hnt-web1-4.png)

## keybindings
- `Alt+M`: toggle the conversation menu; opening focuses the title field
- `Ctrl+Shift+J` / `Ctrl+Shift+K`: jump to the next / previous message
- `Ctrl+Enter` / `Cmd+Enter`: submit the composer or save the active edit
