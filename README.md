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
│   ├── breath.py       # Breath + decision slot
│   ├── decision.py     # Hard MUST/MAY/SILENT budget
│   ├── analytics.py    # Quality index CLI (operator)
│   ├── test_analytics.py
│   └── test_decision.py
├── install/
│   ├── setup.py        # Installer + wizard (name, goal, language, TTS)
│   ├── SOUL.md
│   └── plugins/bibo-clean-output/
├── README.md           # This file (English, default)
├── README.pl.md        # Polish version
├── CHANGELOG.md        # Version history
└── .gitignore
```

**How it works:**
1. Hermes cron wakes the `bibo` profile every hour
2. `scripts/breath.py` loads `brain.json`, time, and a **hard decision slot** (`MUST_WRITE` / `MAY_WRITE` / `SILENT`), then thaws the brain (count + decay) even on silence
3. The model writes the message only if the slot allows it — the plugin enforces `SILENT`
4. If writing → Telegram (text + optional Edge Neural voice bubble via `/voice tts`)
5. After a conversation the agent may add one evidence-backed entry to `wnioski.entries`
5. User replies → gateway has full conversation context
6. Agent updates `brain.json` after each conversation (described in SOUL.md: *Updating brain.json after a conversation*)
7. If there's nothing to say → cron returns `[SILENT]`

> **Change vs. V0:** Cron no longer decides OBSERVE / THINK / MESSAGE / WAIT. It's an alarm clock — sends a conversation opener or `[SILENT]`. All logic lives in the gateway.

---

## Issues & Kanban

- 📋 **Issues:** [github.com/Grandpa1001/hi-bibo/issues](https://github.com/Grandpa1001/hi-bibo/issues)
- 📊 **Project board:** [github.com/users/Grandpa1001/projects/1](https://github.com/users/Grandpa1001/projects/1)

---

## Installation

### Requirements
- [Hermes Agent](https://github.com/nousresearch/hermes) on PATH
- Telegram account + token from [@BotFather](https://t.me/BotFather)
- Your Telegram user ID (message [@userinfobot](https://t.me/userinfobot))
- Model auth in Hermes (Anthropic API key or OAuth)
- `ffmpeg` — without it Edge TTS is sent as a file, not a voice bubble (`brew install ffmpeg` / `sudo apt install ffmpeg`)

### 1. Clone the pack

```bash
cd /opt/data   # or whatever Hermes uses as workdir
git clone https://github.com/Grandpa1001/hi-bibo.git
cd hi-bibo
```

### 2. Run the wizard

```bash
python3 install/setup.py
```

The wizard asks, in order:
1. **Language** — pl / en
2. **Partner name** — 3 random suggestions (Mira, Nox, Olek, …) or your own
3. **Relationship goal** — one contract, e.g. "ship the sprint, no new projects"
4. **Frequency** — rarely / normal / often (this is a hard budget, not a prompt)
5. **TTS** — Edge Neural (`Zofia` / `Marek` for Polish, `Aria` / `Andrew` for English). This is **not** Telegram's built-in voice.
6. **Bot token** and **your user ID**

The script creates the `bibo` profile, copies SOUL + plugin + scripts, writes `.env`, sets TTS/STT in `config.yaml`, installs the breath cron, writes `brain.json`, and starts the gateway.

Non-interactive:

```bash
python3 install/setup.py --yes --language pl --name Mira \
  --goal "ship the sprint" --frequency normal --tts zofia \
  --telegram-token 'TOKEN' --telegram-user-id '123456'
```

### 3. Telegram — first 30 seconds

Open the bot → `/start`, then:

| Command | What it does |
|---|---|
| `/bibo-setup` | In-chat wizard (name, goal, language, TTS, frequency). No LLM. |
| `/voice tts` | Replies as an **Edge Neural voice bubble** (not Telegram TTS) |
| `/bibo-profile` | Partner card |
| `/bibo-analytics` | Index of whether Bibo itself is working better |

`/bibo-setup losuj` suggests new names.

### What is deterministic after install

- **When to write** is computed by `scripts/decision.py`: adaptation 3/day (1/8), partnership 6/day (1/4), plus 12h anti-silence and night quiet. T004 frequency (`rarely`/`often`) overrides the cap. The model does not vote.
- A `SILENT` slot is **enforced** by the plugin.
- Stale mood in `zachowania_biezace` **decays** (48h half-weight, 72h archive) so old “irritated” cannot freeze the agent.
- **Conclusions** go to `brain.json → wnioski.entries` only with evidence.
- Pack TTS: `edge` + locale voice + Whisper `small` for STT (better Polish than `base`).

The old 10-step manual install is replaced by this script.

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
| Voice sounds like cheap Telegram TTS | That's not Edge. Pick Zofia/Marek in the wizard, install `ffmpeg`, then `/voice tts` in chat. |

---

## Testing

1. **Check the gateway:** `hermes profile list` — bibo should show `running`
2. **Check jobs:** read `profiles/bibo/cron/jobs.json`
3. **Check brain:** `cat hi-bibo/brain.json | python3 -m json.tool`
4. **Force a breath:** message @Hi_Bibo_bot "breathe" or wait for the scheduled run
5. **Check logs:** `cat profiles/bibo/logs/agent.log | tail -20`

---

## Quality analytics

A single `brain.json` snapshot cannot tell you whether a prompt or cron change made Bibo better. You need a time series.

Analytics layer:
- `scripts/breath.py` writes a brain snapshot on every breath
- the plugin records inbound/outbound turns (length, hash, hygiene flags — **no message bodies**)
- file: `$BIBO_DIR/logs/analytics.jsonl` (gitignored)

```bash
# on the machine where Bibo lives
BIBO_DIR=/opt/data/hi-bibo python3 /opt/data/hi-bibo/scripts/analytics.py report
BIBO_DIR=/opt/data/hi-bibo python3 /opt/data/hi-bibo/scripts/analytics.py report --json --days 7

# on Telegram (plugin ≥ 1.2)
/bibo-analytics
/bibo-analytics 14
```

**Index 0–100** (behavioral proxy, not a clinical ADHD score), weights:
| Component | Weight | What it measures |
|---|---|---|
| 6h reply rate | 35% | Whether the user replies to Bibo |
| Presence | 25% | Whether Bibo pings after >12h of user silence |
| Learning | 20% | Mean bucket `confidence` in brain.json |
| Hygiene | 20% | No guilt-trips, sycophancy, walls of text, thought leaks |

The report compares **the last N days vs the previous N days**. Verdict `rosnie` / `spada` / `stabilne` requires a ≥5 point move. Too few events → index is `null`, not a guess.

Bibo must **not** load this report into context — otherwise it will optimize the metric instead of the relationship.

---

## Versioning

- **V1** — Prototype: cron-alarm-clock + brain + gateway + Telegram
- **V2** — (planned) Communication form evaluation, auto phase transitions, standalone app

---

## License

MIT
