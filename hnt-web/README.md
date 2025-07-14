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
curl hnt-agent.org/install | sh

# start the server
hnt-web

# open http://127.0.0.1:2027/ in your browser
```

the architecture is vanilla Go (http std lib) + Vanilla JS. the entire server is
one Python executable (hnt-web). the frontend is copied to `$XDG_DATA_HOME` on
build and then served from there

=> you don't need any docker or npm, just Go

it uses hnt-chat as the LLM backend, so all of your messages are plaintext and
simple to manage externally

## ss (as of 2025-06-17)
![1](https://raw.githubusercontent.com/veilm/veilm.github.io/refs/heads/master/static/1750216968-hnt-web.png)

![2](https://raw.githubusercontent.com/veilm/veilm.github.io/refs/heads/master/static/1750217113-hnt-web.png)

![3](https://raw.githubusercontent.com/veilm/veilm.github.io/refs/heads/master/static/1750217128-hnt-web.png)
