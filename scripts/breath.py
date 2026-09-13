#!/opt/hermes/.venv/bin/python3
"""
Hi-Bibo breath controller V2.
Wywołuje Anthropic API bezpośrednio, parsuje JSON response,
zapisuje brain_updates i thoughts do plików,
na stdout wypluwa TYLKO message (lub nic dla OBSERVE/THINK/WAIT).

Używany jako cron script z no_agent=true.
"""

import json
import os
import sys
from datetime import datetime

import anthropic

BIBO_DIR = "/opt/data/hi-bibo"
BRAIN_PATH = os.path.join(BIBO_DIR, "brain.json")
KNOWLEDGE_PATH = os.path.join(BIBO_DIR, "knowledge.md")
PROMPT_PATH = os.path.join(BIBO_DIR, "prompt.md")
THOUGHTS_LOG = os.path.join(BIBO_DIR, "logs", "thoughts.log")

# Ensure logs dir exists
os.makedirs(os.path.join(BIBO_DIR, "logs"), exist_ok=True)


def load_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def append_log(path, text):
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def deep_merge(base, updates):
    """Merge updates into base dict recursively."""
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def get_telegram_history():
    """Try to fetch recent messages from Telegram bot."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        # Try reading from bibo profile .env
        env_path = "/opt/data/profiles/bibo/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("TELEGRAM_BOT_TOKEN="):
                        bot_token = line.strip().split("=", 1)[1]
                        break

    if not bot_token:
        return ""

    try:
        import urllib.request
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=20&timeout=1"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())

        messages = []
        for update in data.get("result", []):
            msg = update.get("message", {})
            text = msg.get("text", "")
            from_user = msg.get("from", {}).get("first_name", "?")
            date = msg.get("date", 0)
            if text:
                dt = datetime.fromtimestamp(date).strftime("%Y-%m-%d %H:%M")
                messages.append(f"[{dt}] {from_user}: {text}")

        if messages:
            return "\n## Ostatnie wiadomości z Telegrama\n" + "\n".join(messages[-10:])
    except Exception:
        pass

    return ""


def main():
    # Load all context
    brain = load_json(BRAIN_PATH)
    knowledge = load_file(KNOWLEDGE_PATH)
    prompt = load_file(PROMPT_PATH)

    # Build context
    now = datetime.now()
    context = f"""## Aktualny czas
Data: {now.strftime('%Y-%m-%d')} ({now.strftime('%A')})
Godzina: {now.strftime('%H:%M')}
Oddech nr: {brain['breath_count'] + 1}

## Stan brain.json
```json
{json.dumps(brain, indent=2, ensure_ascii=False)}
```

## Baza wiedzy
{knowledge}
{get_telegram_history()}"""

    # Call Anthropic API
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        env_path = "/opt/data/profiles/bibo/.env"
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("ANTHROPIC_API_KEY="):
                        api_key = line.strip().split("=", 1)[1]
                        break

    if not api_key:
        print("ERROR: No ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(1)

    # Use Hermes's Anthropic client builder — it auto-detects OAuth tokens
    # (sk-ant-oat*) vs regular API keys (sk-ant-api*) and applies the correct
    # auth headers (Bearer vs x-api-key) plus the Claude-Code identity headers
    # OAuth requires. Falling back to raw anthropic.Anthropic(api_key=...) would
    # send OAuth tokens as x-api-key and get 401.
    try:
        sys.path.insert(0, "/opt/hermes")
        from agent.anthropic_adapter import build_anthropic_client
        client = build_anthropic_client(api_key, base_url="https://api.anthropic.com")
    except Exception as _hermes_import_err:
        # Fallback: plain SDK client (works for regular API keys, fails for OAuth)
        print(
            f"WARN: could not use Hermes anthropic adapter ({_hermes_import_err}); "
            "falling back to plain SDK client (OAuth tokens will fail)",
            file=sys.stderr,
        )
        client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        system=prompt,
        messages=[
            {"role": "user", "content": context}
        ]
    )

    raw_text = response.content[0].text.strip()

    # Parse JSON response
    # Try to extract JSON from response (might have markdown code block)
    json_text = raw_text
    if "```json" in json_text:
        json_text = json_text.split("```json")[1].split("```")[0].strip()
    elif "```" in json_text:
        json_text = json_text.split("```")[1].split("```")[0].strip()

    try:
        result = json.loads(json_text)
    except json.JSONDecodeError:
        # Fallback: log raw response and exit
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        append_log(THOUGHTS_LOG, f"\n[{timestamp}] PARSE ERROR — raw response:\n{raw_text}\n")
        print(raw_text)  # Send raw as fallback
        sys.exit(0)

    action = result.get("action", "WAIT")
    message = result.get("message")
    thoughts = result.get("internal_thoughts", "")
    brain_updates = result.get("brain_updates", {})
    comm_form = result.get("communication_form", "")

    # 1. Apply brain updates
    if brain_updates:
        deep_merge(brain, brain_updates)
        save_json(BRAIN_PATH, brain)

    # 2. Log thoughts
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = (
        f"\n[{timestamp}] Oddech #{brain.get('breath_count', '?')} | "
        f"Action: {action} | Form: {comm_form}\n"
        f"Thoughts: {thoughts}\n"
    )
    if brain_updates:
        log_entry += f"Brain updates: {json.dumps(brain_updates, ensure_ascii=False)}\n"
    append_log(THOUGHTS_LOG, log_entry)

    # 3. Output ONLY message to stdout (goes to Telegram)
    if action == "MESSAGE" and message:
        print(message)
    # For OBSERVE/THINK/WAIT — empty stdout = no delivery


if __name__ == "__main__":
    main()
