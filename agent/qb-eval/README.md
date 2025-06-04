# qb-eval
simple wrapper of the qutebrowser CLI for JavaScript I/O

## installation
```sh
git clone https://github.com/michaelskyba/hinata
cd hinata/agent/qb-eval
./build
```

## usage
you write JS as stdin to `qb-eval`. it writes qutebrowser's final evaluation of
`window.qbe_out` to stdout

example:

```js
// ./example.js
let a = 10
let b = 20
let c = a + b

window.qbe_out = document.title + " - " + c.toString()
```
```sh
$ qutebrowser ":open https://google.com"
$ qb-eval < example.js
Google - 30
```

at least in my testing this is not particularly performant, at least partially
because of the polling that qb-eval does. qutebrowser gives no indication of
when the JS finished, so it periodically checks for a configured output file

(as of 1749062848 this is once per 0.5s, up to 180s)

## architecture
qb-eval does the following:
1. executes your JS
2. creates a Blob object and URL of `window.qbe_out`
3. creates and clicks a download link of that blob URL
4. saves the download to a tmp directory (overwriting your default qutebrowser save dir, for this session)
5. reads the download
