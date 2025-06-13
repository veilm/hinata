# qb-eval
simple wrapper of the qutebrowser CLI for JavaScript I/O

## installation
```sh
git clone https://github.com/michaelskyba/hinata
cd hinata/agent/qb-eval
./build
```

## usage
You write JavaScript to stdin of `qb-eval`. `qb-eval` captures all output from `console.log`, `console.warn`, and `console.error` and writes it to stdout when your script finishes.

Your script is automatically wrapped in an `async` function, which means you can use `await` at the top level for asynchronous operations.

### Synchronous Example

```js
// ./example.js
let a = 10;
let b = 20;
let c = a + b;

console.log(document.title + " - " + c.toString());
```
```sh
$ qutebrowser ":open https://google.com"
$ qb-eval < example.js
Google - 30
```

### Asynchronous Example (Top-Level `await`)

Because your code is run in an async context, you can use `await` directly without wrapping it in an `async` function yourself.

```js
// ./async_example.js
const response = await fetch("https://api.ipify.org?format=json");
const data = await response.json();
console.log(`Your IP address is: ${data.ip}`);
```
```sh
$ qb-eval < async_example.js
Your IP address is: XXX.XXX.XXX.XXX
```

## architecture
qb-eval does the following:
1. Wraps your JavaScript from stdin inside a helper script. This wrapper:
    a. Overrides `console.log`, `console.warn`, and `console.error` to capture all outputs into an array.
    b. Executes your code inside an `async` function, allowing for top-level `await`.
    c. Creates a `Promise` that resolves with the full captured output once your script has finished executing.
2. Executes this combined script in the current qutebrowser page.
3. Executes a second script that waits for the promise to resolve, creates a `Blob` containing the result, creates a temporary download link for this blob, and clicks it.
4. The main `qb-eval` script configures qutebrowser to save this download to a temporary directory without prompting.
5. It then waits for the file to be downloaded, reads its contents, and prints them to stdout.
6. Finally, it cleans up all temporary files and directories.
