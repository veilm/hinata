from openai import OpenAI

# Assumed OPENAI_API_KEY is set
client = OpenAI()

completion = client.chat.completions.create(
    model="gpt-4.1-nano",
    messages=[
        {
            "role": "user",
            "content": "Please output the word `apple` with no other surrounding text or formatting",
        },
    ],
)

print(completion.choices[0].message.content)
