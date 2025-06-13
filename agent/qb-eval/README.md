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

## async usage
`qb-eval` also supports asynchronous operations. If your script sets
`window.qbe_promise` to a `Promise`, `qb-eval` will wait for that promise to
resolve and use its resolved value as the output. If the promise is rejected,
`qb-eval` will output an error message.

This is useful for tasks like fetching data from an API.

Example:

```js
// ./async_example.js
window.qbe_promise = fetch('https://api.ipify.org?format=json')
    .then(response => response.json())
    .then(data => `Your IP address is: ${data.ip}`);
```
```sh
$ qb-eval < async_example.js
Your IP address is: XXX.XXX.XXX.XXX
```

## architecture
qb-eval does the following:
1. executes your JS
2. creates a Blob object and URL of `window.qbe_out` (or the results of `window.qbe_promise`)
3. creates and clicks a download link of that blob URL
4. saves the download to a tmp directory (overwriting your default qutebrowser save dir, for this session)
5. reads the download
