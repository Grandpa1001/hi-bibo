[🇬🇧 English](README.md) | 🇵🇱 Polski

# Hi-Bibo 🫧
<img width="241" height="237" alt="1789408829285" src="https://github.com/user-attachments/assets/d7844c83-35dd-4be1-8a56-99133273befa" />

## Czym jest Bibo?

Bibo to partner do myślenia, zbudowany jako natywny profil agenta [Hermes](https://github.com/NousResearch/hermes). To nie menedżer zadań, nie coach, nie narzędzie dla ADHD — to neutralny partner dla każdego kto chce na głos przemyśleć problem.

**Zasady projektowe (pełne uzasadnienie architektury w [Analiza.MD](Analiza.MD)):**
- 💬 Reaktywny — Bibo odpowiada na Ciebie, zero crona w tle
- 🧠 Minimalna pamięć — pamięta Twoje imię, cel i język. Nic więcej nie przetrwa między sesjami.
- 🎭 Stały charakter — bez ewoluujących cech, bez dryfu
- 🤔 Krytyczne myślenie — kwestionuje konstruktywnie zamiast potakiwać (skill sokratejskich pytań, ładowany na żądanie)
- 🫧 Podpis: każda wiadomość kończy się `,bibo`
- 📱 Telegram, przez wbudowany gateway Hermesa

## Status

🚧 **Aktywny rebuild.** Poprzednia architektura oparta o cron, specyficzna dla ADHD (v1.3) została wycofana na rzecz odchudzonego, natywnego rozwiązania Hermes. Pełny plan, decyzje i uzasadnienie w [Analiza.MD](Analiza.MD).

## Struktura

```
bibo/
├── SOUL.md                 # Tożsamość — kim jest Bibo, styl, format
├── AGENTS.md               # Reguły pracy — onboarding, trigger krytycznego myślenia, anti-sycophancy
├── brain.template.json     # Minimalny trwały stan (imię, cel, język)
├── skills/
│   └── bibo-critical-thinking/   # Pytania sokratejskie, ładowane na żądanie
└── config.yaml              # Konfiguracja modelu + gateway Telegram (wkrótce)
```

## Instalacja

Instalacja wymaga działającego [Hermesa](https://github.com/NousResearch/hermes) na Twojej maszynie lub serwerze.

```bash
hermes profile install github.com/Grandpa1001/hi-bibo
```

_(Proces instalacji jest wciąż walidowany — patrz milestones M1–M5 w Analiza.MD.)_

## Współtworzenie

To repo jest odbudowywane publicznie, iteracyjnie, milestone po milestonie — patrz [Analiza.MD](Analiza.MD) po roadmapę. Issues i PR mile widziane.

## Licencja

Patrz [LICENSE](LICENSE).
