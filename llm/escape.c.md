# escape.c – quick reference

Purpose  
-------  
Stream-oriented filter that **escapes** or **un-escapes** the special chat
role tags

```
<hnt-system> , <hnt-user> , <hnt-assistant>
```

by adding or removing a single leading underscore:

```
<_hnt-system>   <_hnt-user>   <_hnt-assistant>
```

It reads **stdin**, writes the transformed text to **stdout**, and logs
warnings/errors to **stderr**.

Command-line  
------------  

| Flag | Effect |
|------|--------|
| *(none)* | Escape mode (default): add one underscore to every matching tag. |
| `-u` | Un-escape mode: remove one underscore; warn if none exist. |

Return code is `0` on success, `EXIT_FAILURE` on usage / memory errors.

High-level Flow  
---------------  
1. Parse `-u` option (`getopt`).  
2. Character-by-character loop over `stdin` implementing a **deterministic
   finite state machine (FSM)**.  
3. FSM recognises the sequences `<[_]*hnt-(system|user|assistant)>` and the
   closing equivalents.  
4. When a full tag is recognised:
   * `process_match()` emits the modified tag (add/remove underscore).  
5. Any partial/invalid match is flushed verbatim by `flush_buffer_and_reset()`.

Key States (see `#define`s)  
---------------------------  
* `STATE_NORMAL` – pass-through.  
* `STATE_SEEN_LT` – saw `<`.  
* `STATE_SEEN_SLASH` – saw `</`.  
* `STATE_SEEN_UNDERSCORE` – saw one or more `_`.  
* `STATE_CHECK_TAG` – building potential tag name.  
* `STATE_EXPECT_GT` – full tag matched, waiting for `>`.

Important Globals  
-----------------  
* `state` – current FSM state.  
* `buffer[50]`, `buffer_idx` – temporary storage of the possible tag.  
* `underscore_count` – number of leading underscores already present.  
* `matched_tag_base` – `"system"|"user"|"assistant"` when a tag is confirmed.  
* `unescape_mode` – 0 (escape) / 1 (un-escape).

Helper Functions  
----------------  
* `flush_buffer_and_reset()` – write buffer, restore `STATE_NORMAL`.  
* `process_match()` – perform the actual escape / un-escape emission logic.  
* `reprocess_char_in_normal()` – re-feeds a character after flushing.

Buffer safety  
-------------  
If `buffer` nears capacity a warning is issued and the buffer is flushed to
avoid overflow.

Compile  
-------  
```
cc -std=c99 -Wall -O2 escape.c -o escape
```

Typical usage  
-------------  
Escape:   `cat input.txt | ./escape > output.txt`  
Un-escape: `cat input.txt | ./escape -u > output.txt`