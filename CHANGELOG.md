# Changelog

## 0.2.0 — MVP: partner ADHD (2026-09-23)
Full re-analysis in [docs/REANALIZA.md](docs/REANALIZA.md).
- Fixed: `AGENTS.md` was never loaded by Hermes (it reads AGENTS.md from the working
  directory, not the profile). All rules now live in `SOUL.md`.
- Fixed: `brain.json` was read and written by nothing. It is replaced by Hermes built-in memory (`USER.md` / `MEMORY.md`).
- Cost: Telegram/cron get only the `memory` tool (41 KB → 3.4 KB of tool schemas),
  `.no-bundled-skills` blocks ~80 bundled skills, history compacts at ~16k tokens
  (default 256k), background review and curator are off. The fixed prompt went from ~50–58 KB to ~13 KB.
- New: ADHD-aware personality, proactive `bibo-pulse` cron with a zero-token gate
  script (`scripts/bibo_pulse.py`), `install.sh` one-command installer.
- Model: `claude-sonnet-5` via API key by default. OAuth documented as Max + extra usage only.
- Removed: `AGENTS.md`, `brain.template.json`, `skills/bibo-critical-thinking` (folded into SOUL).
  Old analysis and maintenance docs moved to `docs/archiwum/`.

## Unreleased — Hermes-native rebuild (2026-09-21)
- Full architecture rebuild — see [Analiza.MD](Analiza.MD)
- Removed: cron/breath loop, decision slots, migration chain, custom plugin,
  ADHD knowledge base, evolving personality, all v1.3 Python scripts
- Added: `bibo/` package (SOUL.md, AGENTS.md, brain.template.json) —
  reactive, minimal-memory, fixed-personality partner for critical thinking
- Philosophy: neutral partner, not ADHD-specific; no cron; no plugin;
  Sonnet-only; ephemeral session context via Hermes memory

## V1.3 — 2026-09-17 (retired)
- T006: phase caps in code — adaptation 3/day (1/8), partnership 6/day (1/4); T004 frequency still overrides
- Anti-silence: >12h → `MUST_WRITE`, >24h → `silence.failure_24h`; night quiet does not block first breath
- Decay of `zachowania_biezace` (48h half-weight, 72h archive) so stale “irritated” cannot freeze initiative
- Every breath thaws `brain.json` (`breath_count`, `last_updated`, decay) even on `SILENT`
- Plugin 1.4 stamps `last_user_contact` / `last_bibo_message` so the budget survives without analytics.jsonl

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
