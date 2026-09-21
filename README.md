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

The repo root **is** the Hermes profile distribution — `distribution.yaml`
sits next to the actual profile files, which is what `hermes profile install`
expects.

```
distribution.yaml          # Manifest: name, version, description, author
SOUL.md                    # Identity — who Bibo is, style, format
AGENTS.md                  # Working rules — onboarding, critical thinking trigger, anti-sycophancy
brain.template.json        # Minimal persistent state (name, goal, language)
skills/
└── bibo-critical-thinking/
    ├── SKILL.md              # Trigger conditions
    ├── socratic-questions.md # 5 question types
    └── examples.md           # Sample conversations
config.yaml                 # Main model — minimal, only confirmed-real keys
```

Everything else at repo root (`README.md`, `Analiza.MD`, `MAINTENANCE.md`,
`CHANGELOG.md`, `LICENSE`) is project documentation, not profile content —
Hermes ignores it, but it does get copied alongside the profile on install
since the whole repo is the distribution.

## Install

Requires a working [Hermes Agent](https://github.com/NousResearch/hermes-agent) install (`hermes doctor` should be green before you start).

```bash
hermes profile install github.com/Grandpa1001/hi-bibo
```

If you're reinstalling over a previous attempt, add `--force` (preserves
any user data already in the profile):
```bash
hermes profile install github.com/Grandpa1001/hi-bibo --force
```

Verify the profile registered correctly — it should appear in the list, not
just exist as files on disk:
```bash
hermes profile list
```

If it doesn't show up despite `hermes profile install` reporting success,
that was a real bug we hit during development (see [Analiza.MD](Analiza.MD)
for the full diagnosis) — our early `config.yaml` used a made-up schema
that likely failed Hermes' internal validation, silently blocking
registration. The current `config.yaml` only uses keys confirmed against
[Hermes' actual configuration docs](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/configuration.md).
If you still hit this, please open an issue.

Set the required environment variables — per
[Hermes' Telegram docs](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/telegram.md)
these go in `~/.hermes/.env` (global) unless your setup uses a different
`HERMES_HOME`:

```
TELEGRAM_BOT_TOKEN=<token from @BotFather>
TELEGRAM_ALLOWED_USERS=<your Telegram user ID>
ANTHROPIC_API_KEY=<your key>
```

Test in CLI first:
```bash
hermes -p bibo chat
```

Then set up the Telegram gateway — either the interactive wizard (creates
the bot and detects your user ID for you):
```bash
hermes gateway setup
```
or, if you already have a bot token and user ID set as above:
```bash
hermes -p bibo gateway
```

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
