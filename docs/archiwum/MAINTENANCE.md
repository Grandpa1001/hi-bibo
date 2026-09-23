🇬🇧 English | [🇵🇱 Polski](MAINTENANCE.pl.md)

# Bibo — Operations Guide

This is a running checklist for keeping a **live** Bibo install healthy after
you've completed setup (see [README.md](README.md)). It's advice with a
recommended cadence, not a one-time build task — unlike [Analiza.MD](Analiza.MD),
which documents *why* Bibo is built the way it is.

---

## Weekly

**`hermes doctor`** — catches install drift before it becomes a real problem.

**`/usage`** — check actual token spend against the targets below. If you're
consistently over, see "Cost tuning" further down.

## Monthly

### 1. Cost & prompt-size check
```bash
hermes prompt-size --profile bibo
```
- **Target:** static prompt overhead (SOUL.md + AGENTS.md) under 1500 tokens
- **Target:** monthly cost under $5 (compare against `/usage` history)
- If either target is blown: check whether `prompt_cache: true` in
  `config.yaml` is actually being honored by your Hermes version, and
  whether `skills.auto_load` is still empty (it should be — the critical
  thinking skill loads on demand, not always).

### 2. Security audit
```bash
hermes security audit
```
This is a dependency-chain scan, not a full security certification — read
the tutorial's warning on this before assuming it means "safe." Pair it with
a manual check:
- Is `TELEGRAM_BOT_TOKEN` / `ANTHROPIC_API_KEY` still sitting in a plaintext
  `.env`, or moved to `hermes secrets`? Move it if not.
- Any plugin, skill, or MCP server installed that you can't explain why it's
  there? Remove it.

### 3. Self-audit (the agent inspects itself)
Run this exact prompt against Bibo (from the Hermes tutorial, translated —
keep it as-is, don't paraphrase, it's designed to force a no-changes-without-approval audit):

```
Przeprowadź audyt tej instalacji Hermesa bez wprowadzania jakichkolwiek zmian.
Przeanalizuj bieżący profil, routing modeli, bazowy rozmiar promptu, pamięć
i kontekst projektów, zainstalowane skills, włączone narzędzia, wtyczki,
serwery MCP, zadania cron, ostatnie błędy, logi, stan kopii zapasowych,
ustawienia zatwierdzeń oraz stan aktualizacji i bezpieczeństwa. Wskaż
elementy nieużywane, zduplikowane, przestarzałe, generujące zbędne koszty
lub umieszczone w niewłaściwej warstwie. Oddziel zweryfikowane fakty od
rekomendacji. Uporządkuj sugerowane zmiany według ich praktycznego wpływu
i poczekaj na moją zgodę przed zmodyfikowaniem czegokolwiek.
```

Save the output to `logs/audit-YYYY-MM.md`. Review the recommendations,
apply only what you actually agree with — manually, not by letting the
agent auto-apply.

## Quarterly

### Restore drill
A backup you've never restored is a guess, not a plan.
```bash
hermes backup
# on a throwaway VM or container:
hermes import <backup file>
hermes doctor
```
If this fails, your real backup plan just failed too — fix it now, not
during an actual outage.

### Token rotation
Rotate `TELEGRAM_BOT_TOKEN` via @BotFather. Update `hermes secrets` (or `.env`
if you haven't migrated yet — see monthly security check above).

## As-needed

### Cost tuning
If monthly cost is consistently over $5 despite prompt caching:
1. Check `/usage` breakdown — is it mostly input tokens (context) or output?
2. If input-heavy: session history (5-10 exchanges per Etap 3 decision #15)
   may be too generous for your usage pattern — consider trimming.
3. If still high: the `claude-haiku-4-5-20251001` fallback in `config.yaml`
   is only for outages, not routine routing (per non-goals in Analiza.MD —
   "Auxiliary model routing" was deliberately rejected). Revisit that
   decision only if cost becomes the dominant constraint.

### Backup destination setup (one-time, do this before you need it)
Configure `hermes backup` to push to Backblaze B2 or S3 — **not** a folder
on the same VPS. A backup that dies with the machine it protects isn't a
backup.

---

## Why this file exists separately from Analiza.MD

Analiza.MD is the architecture decision record — it explains *why* Bibo has
no cron, no plugin, minimal memory. Milestones M6 (optimization), M7
(recovery/security), M8 (self-audit) in that document were originally
build-once checklist items, but they're actually recurring operational
practices. This file is where they live now, as a living document you
actually reference on a schedule — Analiza.MD stays a historical record of
the rebuild decision.
