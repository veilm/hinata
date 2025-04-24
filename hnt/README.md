# hnt
note: this might be deleted at any time if I decide on a different design or
realize the Unix philosophy is poisonous or something

## build
```
git clone https://github.com/michaelskyba/hinata
cd hinata/hnt
./build
```

## basic usage
```
export OPENROUTER_API_KEY="my api key"
echo hello | ./hnt

# system prompt using -s or --system
echo 2027 | ./hnt -s "Please repeat the given number verbatim"
```
(defaults to `openrouter/deepseek/deepseek-chat-v3-0324:free` as the model)

## supported model providers
you can specify a model with `-m` or `--model`

### [OpenRouter](https://openrouter.ai/settings/keys)
```
export OPENROUTER_API_KEY="my api key"
echo hello | ./hnt -m openrouter/qwen/qwen2.5-coder-7b-instruct
```

### [DeepSeek](https://platform.deepseek.com/api_keys)
```
export DEEPSEEK_API_KEY="my api key"
echo hello | ./hnt -m deepseek/deepseek-chat
```

### [OpenAI](https://platform.openai.com/settings/organization/api-keys)
```
export OPENAI_API_KEY="my api key"
echo hello | ./hnt -m openai/gpt-4o
```

### [Google](https://aistudio.google.com/apikey)
```
export GEMINI_API_KEY="my api key"
echo hello | ./hnt -m google/gemini-1.5-flash-latest
```

### local
no support yet. I'm an ill , homeless peasant with no GPU
