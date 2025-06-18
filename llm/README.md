# hnt-llm
note: this might be deleted at any time if I decide on a different design or
realize the Unix philosophy is poisonous or something

## build
```
git clone https://github.com/veilm/hinata
cd hinata/llm
./build
```

## basic usage
```
export OPENROUTER_API_KEY="my api key"
echo hello | hnt-llm

# system prompt using -s or --system
echo 2027 | hnt-llm -s "Please repeat the given number verbatim"
```
(The model is specified by the `--model` CLI argument, or the `$HINATA_LLM_MODEL` environment variable if set, or finally defaults to `openrouter/deepseek/deepseek-chat-v3-0324:free`)

## supported model providers
you can specify a model with `-m` or `--model`

### [OpenRouter](https://openrouter.ai/settings/keys)
```
export OPENROUTER_API_KEY="my api key"
echo hello | hnt-llm -m openrouter/qwen/qwen2.5-coder-7b-instruct
```

### [DeepSeek](https://platform.deepseek.com/api_keys)
```
export DEEPSEEK_API_KEY="my api key"
echo hello | hnt-llm -m deepseek/deepseek-chat
```

### [OpenAI](https://platform.openai.com/settings/organization/api-keys)
```
export OPENAI_API_KEY="my api key"
echo hello | hnt-llm -m openai/gpt-4o
```

### [Google](https://aistudio.google.com/apikey)
```
export GEMINI_API_KEY="my api key"
echo hello | hnt-llm -m google/gemini-2.5-flash-preview-04-17
```

### local
no support yet. I'm an ill , homeless peasant with no GPU

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
```
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
```
echo test | hnt-llm --debug-unsafe
```
