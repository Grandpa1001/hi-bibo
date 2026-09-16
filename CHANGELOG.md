# Changelog

## V1.2 — 2026-09-16
- Real installer + wizard: `python3 install/setup.py`
- Partner contract in `brain.json` (name, language, goal, TTS, frequency)
- Deterministic speak slot (`scripts/decision.py`) enforced by the plugin
- Pack TTS: Edge Neural (Zofia/Marek/Aria/Andrew) + Whisper `small`, not Telegram TTS
- Telegram `/bibo-setup` to finish or change identity without an LLM
- `wnioski.entries` — conclusions only with evidence

## V1.1 — 2026-09-16
- Quality analytics: `scripts/analytics.py` + `logs/analytics.jsonl`
- Plugin 1.2: `post_llm_call` telemetry and `/bibo-analytics`
- Breath script emits a brain snapshot on every run
- Paths honor `BIBO_DIR` (default `/opt/data/hi-bibo`)

## V1 — 2026-09-13
- Initial prototype
- Core loop: OBSERVE / THINK / MESSAGE / WAIT
- Brain structure: 9 buckets
- Knowledge base: ADHD research + anti-patterns
- Platform: Hermes cron → Telegram bot
- Anti-sycophancy rules
- Onboarding flow
