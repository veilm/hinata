# ❄️ hnt-llm

## build
```sh
git clone https://github.com/veilm/hinata
./hinata/llm/build
```

## basic usage
```sh
export OPENROUTER_API_KEY="my api key"
echo hello | hnt-llm --model openrouter/deepseek/deepseek-r1

# system prompt using -s or --system
echo 2027 | hnt-llm -s "Please repeat the given number verbatim"
```

The model is determined by:
- the `-m` or `--model` CLI argument
- fallback: the `$HINATA_LLM_MODEL` environment variable
- second fallback: `openrouter/deepseek/deepseek-chat-v3-0324:free`

you can set `--include-reasoning` to also receive reasoning tokens, for models
that produce them. the output format has no sophisticated escaping and is simply
```
<think>
thinking here
</think>
summary here
```

## on-device key management
besides using the `*_API_KEY` env variables, you can use the built-in (bloat)
key manager:
```sh
# save a key
# (this will prompt you to paste it in)
hnt-llm save-key OPENAI_API_KEY

# list
hnt-llm list-keys

# delete
hnt-llm delete-key OPENAI_API_KEY

# by intention, there's no get-key or fetch-key command
```

if you have a given key saved, it will be used in cases where you request that
provider but do not have the respective env variable set

your direct API keys are encrypted with XOR against a generated private key, but
the private key is stored in plaintext, with some appropriate filesystem perms.
it's secure enough that someone casually browsing your filesystem will be
unlikely to find your keys

## supported model providers
### [OpenRouter](https://openrouter.ai/settings/keys)
```sh
export OPENROUTER_API_KEY="my api key"
echo hello | hnt-llm -m openrouter/qwen/qwen2.5-coder-7b-instruct
```

### [DeepSeek](https://platform.deepseek.com/api_keys)
```sh
export DEEPSEEK_API_KEY="my api key"
echo hello | hnt-llm -m deepseek/deepseek-chat
```

### [OpenAI](https://platform.openai.com/settings/organization/api-keys)
```sh
export OPENAI_API_KEY="my api key"
echo hello | hnt-llm -m openai/gpt-4o
```

### [Google](https://aistudio.google.com/apikey)
```sh
export GEMINI_API_KEY="my api key"
echo hello | hnt-llm -m google/gemini-2.5-flash-preview-04-17
```

## XML history input
you can provide conversation history via stdin using XML tags:
- `<hnt-system>`
- `<hnt-user>`
- `<hnt-assistant>`

any content outside of these tags will be treated final user message if given,
for consistency. if a system prompt is provided via `-s`, it is inserted as the
very first message in the request, before any `<hnt-system>` content

this would send msg1 and msg2 as consecutive system messages, with "msg5"
(surrounding space trimmed) as the final user message:
```sh
echo "
<hnt-system>msg2</hnt-system>
<hnt-user>msg3</hnt-user>
<hnt-assistant>msg4</hnt-assistant>
msg5
" | hnt-llm -s msg1
```

XML is simpler to construct manually and in scripts than JSON

### escaping
(`hnt-chat`/`hnt-edit` takes care of this automatically)

what if you want to include XML tags literally? this is an unideal design
dilemma but imo the best solution is a custom escape system:
- if we encounter one of our special tags, escape it by placing an additional
underscore before the name
- unescape by removing an underscore

the escaping happens in whatever hnt-llm wrapper you have that is constructing
messages. you e.g. take your raw assistant message, escape it, then wrap it in
real `<hnt-assistant></hnt-assistant>` closing tags as part of your final
hnt-llm stdin construction. nothing abnormal; it's just as you would if passing
JSON

the unescaping happens internally in `hnt-llm`. for each message it finds
(including a system message provided through `--system`, for consistency, even
though it likely doesn't need it), it will unescape it as it constructs the
internal linked list of messages. the LLM sees your raw unescaped original
message, of course

`hnt-escape` is provided as a util for this.
```sh
# escape
echo "this is my<hnt-system>literal system prompt" | hnt-escape
# --> this is my<_hnt-system>litearl system prompt

# unescape
echo "this is my<hnt-system>literal system prompt" | hnt-escape | hnt-escape -u
# --> this is my<hnt-system>literal system prompt
# (should always be equal to original input)
```

- a double escaped `<__hnt-system>` is significantly more human-readable than
`&apos;lt;hnt-system&apos;gt;`. this is more feasible for occasional manual
construction of history
- with this system, escaping will only ever be used at all very rarely. our
meta tags like `<hnt-system>` are unlikely to show up in natural messages,
unlike special XML chars (`"'<>&`) which are abundant

you can mask the `hnt-escape` binary or just patch the call if you really need a
standard escape format. but if you think you do, you're likely misunderstanding
the flow and trying to intercept too late

## debugging
you can use the `--debug-unsafe` flag to examine the raw LLM request/response
for your query. **This will include your API key in the output.**
```sh
echo test | hnt-llm --debug-unsafe
```
