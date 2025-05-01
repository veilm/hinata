# hnt-llm
note: this might be deleted at any time if I decide on a different design or
realize the Unix philosophy is poisonous or something

## build
```
git clone https://github.com/michaelskyba/hinata
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
(defaults to `openrouter/deepseek/deepseek-chat-v3-0324:free` as the model)

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

- TODO `hnt-escape` for escaping

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

## debugging
you can use the `--debug-unsafe` flag to examine the raw LLM request/response
for your query. **This will include your API key in the output.**
```
echo test | hnt-llm --debug-unsafe
```
