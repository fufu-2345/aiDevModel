import requests

def generate_text(prompt: str):
    payload = {"model": "llama3", "prompt": prompt}
    r = requests.post("http://localhost:11434/api/generate", json=payload)
    try:
        return r.json().get("response", "no response")
    except:
        return "error calling ollama"