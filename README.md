🇬🇧 English | [🇵🇱 Polski](README.pl.md)

# Hi-Bibo 🫧
<img width="241" height="237" alt="1789408829285" src="https://github.com/user-attachments/assets/d7844c83-35dd-4be1-8a56-99133273befa" />

## What is Bibo?

Bibo is a thinking partner, built as a native [Hermes](https://github.com/NousResearch/hermes) agent profile. It's not a task manager, not a coach, not an ADHD tool — it's a neutral partner for anyone who wants to think through a problem out loud.

**Design principles (see [Analiza.MD](Analiza.MD) for the full architecture rationale):**
- 💬 Reactive — Bibo responds to you, no background cron polling
- 🧠 Minimal memory — remembers your name, your goal, your language. Nothing else persists between sessions.
- 🎭 Fixed personality — no evolving traits, no drift
- 🤔 Critical thinking — questions constructively instead of agreeing by default (Socratic questions skill, loaded on demand)
- 🫧 Signature: every message ends with `,bibo`
- 📱 Telegram, via Hermes' built-in gateway

## Status

🚧 **Active rebuild.** The previous cron-based, ADHD-specific architecture (v1.3) has been retired in favor of a lean, Hermes-native design. See [Analiza.MD](Analiza.MD) for the complete plan, decisions, and rationale.

## Structure

```
bibo/
├── SOUL.md               # Identity — who Bibo is, style, format
├── AGENTS.md              # Working rules — onboarding, critical thinking trigger, anti-sycophancy
├── brain.template.json    # Minimal persistent state (name, goal, language)
├── skills/
│   └── bibo-critical-thinking/   # Socratic questions, loaded on demand
└── config.yaml             # Model + Telegram gateway config (coming soon)
```

## Install

Install requires a working [Hermes](https://github.com/NousResearch/hermes) setup on your machine or server.

```bash
hermes profile install github.com/Grandpa1001/hi-bibo
```

_(Install flow is still being validated — see Analiza.MD milestones M1–M5.)_

## Contributing

This repo is being rebuilt in public, iteratively, one milestone at a time — see [Analiza.MD](Analiza.MD) for the roadmap. Issues and PRs welcome.

## License

See [LICENSE](LICENSE).
