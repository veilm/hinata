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
installationl and then hnt-web serves from there

=> you don't need any docker or npm, just Go

it uses hnt-chat as the LLM backend, so all of your messages are plaintext and
simple to manage externally

## ss
![ss 1](https://sucralose.moe/static/hnt-web-0.png)

![ss 2](https://sucralose.moe/static/hnt-web-1.png)

![ss 3](https://sucralose.moe/static/hnt-web-2.png)
