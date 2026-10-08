import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY",""))

r = client.chat.completions.create(
    model    = "qwen/qwen3.8-27b",
    messages = [
        {"role": "system",
         "content": "You are a SQL expert. Return only SQL."},
        {"role": "user",
         "content": "Write a SQL query to get top 10 companies by market_cap from a table called metrics joined with companies on ticker. Return only the SQL."}
    ],
    temperature = 0.0,
    max_tokens  = 300,
)

msg       = r.choices[0].message
content   = getattr(msg, "content",   "") or ""
reasoning = getattr(msg, "reasoning", "") or ""

print(f"Content length:   {len(content)}")
print(f"Reasoning length: {len(reasoning)}")
print(f"Content:   '{content[:200]}'")
print(f"Reasoning: '{reasoning[:200]}'")
print(f"Finish reason: {r.choices[0].finish_reason}")
print(f"Tokens: {r.usage}")