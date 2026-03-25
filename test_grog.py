import requests, os

key = os.environ.get("GROQ_API_KEY", "NON DEFINIE")
print(f"Clé utilisée: {key[:10]}...")

r = requests.post(
    "https://api.groq.com/openai/v1/chat/completions",
    headers={"Authorization": f"Bearer {key}"},
    json={
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": "Bonjour"}],
        "max_tokens": 50
    }
)
print(r.status_code, r.json())