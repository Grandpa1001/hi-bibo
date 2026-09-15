🇬🇧 English | [🇵🇱 Polski](README.pl.md)

# Hi-Bibo 🫧

## What is Hi-Bibo?

Hi-Bibo is an autonomous AI partner for people with ADHD. It's not a chatbot, not a task manager. It's an agent that lives 24/7, breathes every hour, builds a mental model of the user, and adapts its communication style.

**Key features:**
- 🧠 Its own memory (`brain.json`) — learns WHO you are
- ⏰ Cron = alarm clock — reads brain, triggers gateway
- 🧩 Gateway = the brain — the only agent that thinks and writes
- 🚫 Anti-sycophancy — doesn't yes-you, holds up a mirror
- 📱 Works via Telegram — like a message from a partner
- 🎭 8 communication forms — rotates to avoid monotony
- 🫧 Signature: "Hi ... ,bibo"

## Architecture

```
hi-bibo/
├── brain.json          # Dynamic user model (gitignored, private)
├── brain.template.json # Empty template (in repo)
├── knowledge.md        # Static ADHD knowledge base
├── prompt.md           # Bibo system prompt (main file)
├── scripts/
│   └── breath.py       # Breath script — brain + time
├── install/
│   ├── SOUL.md         # Character + sections: brain update after conversation, cron breaths
│   └── plugins/bibo-clean-output/
├── README.md           # This file (English, default)
├── README.pl.md        # Polish version
├── CHANGELOG.md        # Version history
└── .gitignore
```

**How it works:**
1. Hermes cron (alarm clock) wakes the agent every hour on the `bibo` profile
2. `scripts/breath.py` loads `brain.json` + current time (no knowledge.md)
3. Gateway — the only agent that thinks — reads brain and decides whether to write
4. If writing → message goes to Telegram and is mirrored to the gateway session (`attach_to_session: true`)
5. User replies → gateway has full conversation context
6. Agent updates `brain.json` after each conversation (described in SOUL.md: *Updating brain.json after a conversation*)
7. If there's nothing to say → cron returns `[SILENT]`

> **Change vs. V0:** Cron no longer decides OBSERVE / THINK / MESSAGE / WAIT. It's an alarm clock — sends a conversation opener or `[SILENT]`. All logic lives in the gateway.

---

## Issues & Kanban

- 📋 **Issues:** [github.com/Grandpa1001/hi-bibo/issues](https://github.com/Grandpa1001/hi-bibo/issues)
- 📊 **Project board:** [github.com/users/Grandpa1001/projects/1](https://github.com/users/Grandpa1001/projects/1)

---

## Step-by-step Installation

### Requirements
- [Hermes](https://github.com/nousresearch/hermes) installed and running
- Telegram account
- Anthropic API key (for the LLM)

### Step 1: Create a Telegram bot

1. Open Telegram → search for **@BotFather**
2. Send `/newbot`
3. Name: `Hi-Bibo` (or anything you like)
4. Username: `hi_bibo_bot` (or any available name)
5. **Copy the token** — you'll need it in step 3

### Step 2: Clone the repo

```bash
cd /opt/data  # or your HERMES_HOME
git clone https://github.com/Grandpa1001/hi-bibo.git
cd hi-bibo

# Create brain.json from template
cp brain.template.json brain.json
```

### Step 3: Create the Hermes `bibo` profile

```bash
hermes profile create bibo --no-skills \
  --description "Hi-Bibo: autonomous AI partner for people with ADHD"
```

### Step 4: Configure the bibo profile .env

Edit `/opt/data/profiles/bibo/.env`:

```env
ANTHROPIC_API_KEY=«redacted:sk-…»
TELEGRAM_BOT_TOKEN=YOUR_BOTFATHER_TOKEN
TELEGRAM_ALLOWED_USERS=YOUR_TELEGRAM_USER_ID
```

> **How to find your Telegram User ID:** message @userinfobot on Telegram.

### Step 5: Configure the bibo profile config.yaml

Edit `/opt/data/profiles/bibo/config.yaml` — add these sections:

```yaml
agent:
  max_turns: 50
  reasoning_effort: medium
gateway:
  telegram:
    - hermes-telegram
platforms:
  telegram:
    enabled: true
    home_channel:
      platform: telegram
      chat_id: 'YOUR_TELEGRAM_USER_ID'
      name: YourName
      user_id: 'YOUR_TELEGRAM_USER_ID'
```

### Step 6: Set up the bibo profile SOUL.md

Copy the ready-made file from `install/`:

```bash
cp /opt/data/hi-bibo/install/SOUL.md /opt/data/profiles/bibo/SOUL.md
```

SOUL.md defines Bibo's character, communication rules (Hi..., ,bibo), the ban on sending internal thoughts to the user, plus new sections: *Updating brain.json after a conversation* and *Cron breaths*.

### Step 6b: Install the `bibo-clean-output` plugin

The plugin does three things:
1. **Filters Bibo's thoughts** — strips everything after the first `bibo` (internal reasoning after tool_call goes to `logs/thoughts.log`, not the user)
2. **Guards brain.json structure** — if Bibo drops a top-level key during a breath, the plugin restores it from `brain.template.json`
3. **Slash command `/bibo-profile`** — shows a partner card on Telegram (phase, breaths, character traits, what works / what doesn't)

Installation:
```bash
mkdir -p /opt/data/profiles/bibo/plugins
cp -r /opt/data/hi-bibo/install/plugins/bibo-clean-output /opt/data/profiles/bibo/plugins/

# Enable the plugin in the bibo profile config.yaml:
HERMES_HOME=/opt/data/profiles/bibo hermes config set plugins.enabled '["bibo-clean-output"]'

# Silence the system "💾 Self-improvement review" notification (not from Bibo):
HERMES_HOME=/opt/data/profiles/bibo hermes config set display.memory_notifications off

# Disable the background_review mechanism entirely — Bibo works exclusively
# on its own brain.json + thoughts.log; Hermes's built-in memory isn't needed
# and only adds noise + background API costs.
HERMES_HOME=/opt/data/profiles/bibo hermes config set auxiliary.background_review.enabled false
```

**Controlling the thought filter:** the `debug_mode` field in `brain.json`:
- `false` (production) — user sees only Bibo's message, thoughts go to `logs/thoughts.log`
- `true` (debug) — plugin doesn't filter, user sees everything

**`/bibo-profile` command on Telegram**

Returns a compact "partner card" — data about Bibo itself (not the user):

- Current phase (adaptation / partnership / silence) + description
- Breath count + timestamp of last brain update
- `debug_mode` flag state
- 6 character parameters as text bars (directness, patience, humor, provocativeness, emotionality, curiosity) — evolve through conversation
- `co_dziala.skuteczne` — communication forms that worked
- `co_dziala.nieskuteczne` — forms the user rejected

Pure file read — nothing goes to the LLM, spam it for free. On Telegram it may be hidden in the command list (if the bot has >60 registered commands), but still works when typed manually.

### Step 7: Copy the breath script

```bash
mkdir -p /opt/data/profiles/bibo/scripts
cp /opt/data/hi-bibo/scripts/breath.py /opt/data/profiles/bibo/scripts/breath.py
```

### Step 8: Start the bibo gateway

```bash
hermes gateway start --profile bibo
```

Verify it's running:
```bash
hermes profile list
# bibo should show status: running
```

### Step 9: Create the cron job (hourly breath)

⚠️ **IMPORTANT:** The cron job MUST be created from within the bibo profile (via the Telegram bot or the bibo gateway). NOT via `hermes cron create` from the terminal — that creates the job on the default profile!

**Method: Message @Hi_Bibo_bot on Telegram:**

```
/cron every 1h bibo-breath
```

Or create manually in `/opt/data/profiles/bibo/cron/jobs.json`:

```json
{
  "jobs": [
    {
      "id": "GENERATE_UNIQUE_ID",
      "name": "bibo-breath",
      "prompt": "You are Bibo. This is your breath.\nRead prompt.md and brain.json.\nDecide whether to write.\nMESSAGE → content. SILENT → [SILENT].\nStart with 'Hi', end with ',bibo'.",
      "script": "breath.py",
      "no_agent": false,
      "attach_to_session": true,
      "origin": {
        "platform": "telegram",
        "chat_id": "YOUR_TELEGRAM_USER_ID",
        "user_id": "YOUR_TELEGRAM_USER_ID",
        "chat_type": "private"
      },
      "continuity": true,
      "schedule": {
        "kind": "interval",
        "minutes": 60,
        "display": "every 60m"
      },
      "enabled": true,
      "deliver": "telegram:YOUR_TELEGRAM_USER_ID",
      "workdir": "/opt/data/hi-bibo"
    }
  ],
  "updated_at": "2026-09-13T16:00:00+00:00"
}
```

After editing, restart the gateway:
```bash
hermes gateway stop --profile bibo
hermes gateway start --profile bibo
```

> **Note on `schedule`:** Hermes cron for `kind: interval` reads the `minutes` field. The format `"seconds": 3600` doesn't work — the job falls into `state: error` with *"Failed to compute next run"*. Use `"minutes": N`.

> **Note on `no_agent: false`:** This cron **must** run in hermes-agent mode (`no_agent: false`), not script-only. Reason: `breath.py` doesn't call Anthropic on its own — it only provides context (brain.json, time) on stdout. The LLM is invoked by hermes-agent, which inherits the gateway's authentication (including OAuth). Setting `no_agent: true` would require the script to authenticate with Anthropic itself — and OAuth tokens `sk-ant-oat*` don't work as regular API keys.

> **Note on `attach_to_session: true`:** Cron output is mirrored to the gateway's Telegram session. This way the user's reply lands in the same thread and the gateway has full conversation context.

### Step 10: Message the bot

Open Telegram → @Hi_Bibo_bot → `/start`

Bibo will reply at the next breath (max 1h) or immediately if the gateway is active.

---

## Known Pitfalls

| Problem | Solution |
|---------|----------|
| `hermes cron create` creates job on default | Create cron from Telegram on the bibo bot, or manually in `profiles/bibo/cron/jobs.json` |
| `HERMES_PROFILE=bibo hermes cron list` shows default jobs | CLI cron ignores HERMES_PROFILE — known quirk. Profile jobs live in `profiles/bibo/cron/jobs.json` |
| `hermes send` sends via the default bot | `hermes send` always reads `.env` from HERMES_HOME, not the profile. Use the bibo gateway for delivery. |
| Message came from Hermes instead of Hi-Bibo | Cron fired on the default profile. Make sure the job exists ONLY in `profiles/bibo/cron/jobs.json` |
| `Script not found: breath.py` | Script must be in `profiles/bibo/scripts/breath.py` |
| Cron `state=error`, `Failed to compute next run` | Schedule has `"seconds": N` instead of `"minutes": N`. Hermes cron for `kind: interval` only reads `minutes`. |
| Cron logs `401 API key is invalid` in `breath.py` | Job has `no_agent: true` — script tries to call Anthropic directly. Change to `no_agent: false` so hermes-agent calls the LLM (inherits OAuth from the gateway). |
| Getting bare `bibo` with no content every hour | Bibo correctly returns `[SILENT]` when there's nothing to say, but thought-filtering plugins may turn it into bare `bibo`. Fix: `bibo-clean-output` plugin must pass `[SILENT]` through unchanged. |
| "💾 Self-improvement review: ..." message from Hermes | Hermes's built-in `background_review` runs alongside Bibo's brain.json. Disable: `hermes config set auxiliary.background_review.enabled false` on the bibo profile. |

---

## Testing

1. **Check the gateway:** `hermes profile list` — bibo should show `running`
2. **Check jobs:** read `profiles/bibo/cron/jobs.json`
3. **Check brain:** `cat hi-bibo/brain.json | python3 -m json.tool`
4. **Force a breath:** message @Hi_Bibo_bot "breathe" or wait for the scheduled run
5. **Check logs:** `cat profiles/bibo/logs/agent.log | tail -20`

---

## Versioning

- **V1** — Prototype: cron-alarm-clock + brain + gateway + Telegram
- **V2** — (planned) Communication form evaluation, auto phase transitions, standalone app

---

## License

MIT
