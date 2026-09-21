🇬🇧 English | [🇵🇱 Polski](README.pl.md)

# Hi-Bibo 🫧
<img width="241" height="237" alt="1789408829285" src="https://github.com/user-attachments/assets/d7844c83-35dd-4be1-8a56-99133273befa" />

## What is Bibo?

Bibo is a thinking partner, built as a native [Hermes](https://github.com/NousResearch/hermes) agent profile. It's not a task manager, not a coach, not an ADHD tool — it's a neutral partner for anyone who wants to think through a problem out loud.

**Design principles** (see [Analiza.MD](Analiza.MD) for the full architecture rationale):
- 💬 Reactive — Bibo responds to you, no background cron polling
- 🧠 Minimal memory — remembers your name, your goal, your language. Nothing else persists between sessions.
- 🎭 Fixed personality — no evolving traits, no drift
- 🤔 Critical thinking — questions constructively instead of agreeing by default (Socratic questions skill, loaded on demand)
- 🫧 Signature: every message ends with `,bibo`
- 📱 Telegram, via Hermes' built-in gateway

## Status

🚧 **Active rebuild, freshly built, not yet validated on a live Hermes install.** The previous cron-based, ADHD-specific architecture (v1.3) has been fully retired. See [Analiza.MD](Analiza.MD) for the complete plan, all 24 decisions, and the validation against the Hermes tutorial's 14 layers.

## Structure

```
bibo/
├── SOUL.md                 # Identity — who Bibo is, style, format
├── AGENTS.md                # Working rules — onboarding, critical thinking trigger, anti-sycophancy
├── brain.template.json      # Minimal persistent state (name, goal, language)
├── skills/
│   └── bibo-critical-thinking/
│       ├── SKILL.md             # Trigger conditions
│       ├── socratic-questions.md # 5 question types
│       └── examples.md          # Sample conversations
└── config.yaml               # Model, fallback, gateway, cron (empty — Bibo is reactive)
```

## Install

Requires a working [Hermes](https://github.com/NousResearch/hermes) install (`hermes doctor` should be green before you start).

**Option A — if your Hermes version supports remote profile install:**
```bash
hermes profile install github.com/Grandpa1001/hi-bibo
```

**Option B — manual (works with any Hermes version):**
```bash
git clone https://github.com/Grandpa1001/hi-bibo.git
hermes profile create bibo --no-skills --description "Bibo — thinking partner"
cp -r hi-bibo/bibo/* "$HERMES_HOME/profiles/bibo/"   # adjust HERMES_HOME to your setup
```

Then set the required environment variables in the profile's `.env` (or via `hermes secrets`):

```
TELEGRAM_BOT_TOKEN=<token from @BotFather>
TELEGRAM_ALLOWED_USERS=<your Telegram user ID>
ANTHROPIC_API_KEY=<your key>
```

Verify and start:
```bash
hermes doctor
hermes gateway start --profile bibo
```

`config.yaml` ships with `prompt_cache: true`, a `claude-sonnet-4-6` main model with `claude-haiku-4-5-20251001` fallback, no plugins, and an empty cron (Bibo only responds — it doesn't poll in the background). None of this has been run against a live Hermes instance yet — if something doesn't match your Hermes version's exact config schema, that's expected at this stage; open an issue with what you found.

## First contact

Bibo has no onboarding wizard — the first exchange itself is the onboarding, per `AGENTS.md`:
1. Bibo asks your name.
2. Bibo asks what you want to think through, or what you're stuck on.
3. That's it — no further setup questions. Bibo remembers your name, your goal, and your language; nothing else persists.

## Troubleshooting

- `hermes doctor` — checks the install itself
- `hermes prompt-size` — shows the static prompt overhead (SOUL + AGENTS); should stay well under 2k tokens per [Analiza.MD](Analiza.MD) targets
- If Bibo doesn't load the `bibo-critical-thinking` skill when you expect it to, check the trigger conditions in `skills/bibo-critical-thinking/SKILL.md` — it's meant to stay quiet during small talk

## Keeping it healthy

Once installed, see [MAINTENANCE.md](MAINTENANCE.md) for a recurring
checklist — weekly `hermes doctor`, monthly cost/security checks, quarterly
restore drills. That's ongoing operations; this README only covers getting
started.

## Contributing

This repo is being rebuilt in public, iteratively — see [Analiza.MD](Analiza.MD) for the roadmap and open milestones. Issues and PRs welcome, especially reports of what breaks on real Hermes installs.

## License

See [LICENSE](LICENSE).
