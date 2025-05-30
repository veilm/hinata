# hnt-web
`hnt-web`: a minimal web app wrapping `hnt-chat`

- features ❌
- budget ❌
- UX ❌
- active users ❌
- GitHub stars ❌
- X reposts ❌
- brain damage ✅ (minimalism™)

## install (uniquely easy)
```
./build

# start the server
hnt-web
```

the architecture is FastAPI + Vanilla JS. the entire server is one Python
executable (hnt-web). the frontend is copied to `$XDG_DATA_HOME` on build and
then served from there

=> you don't need any docker or npm, just uv (for fastapi and uvicorn)

it uses hnt-chat as the LLM backend, so all of your messages are plaintext and
simple to manage externally
