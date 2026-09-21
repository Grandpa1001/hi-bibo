[🇬🇧 English](README.md) | 🇵🇱 Polski

# Hi-Bibo 🫧
<img width="241" height="237" alt="1789408829285" src="https://github.com/user-attachments/assets/d7844c83-35dd-4be1-8a56-99133273befa" />

## Czym jest Bibo?

Bibo to partner do myślenia, zbudowany jako natywny profil agenta [Hermes](https://github.com/NousResearch/hermes). To nie menedżer zadań, nie coach, nie narzędzie dla ADHD — to neutralny partner dla każdego kto chce na głos przemyśleć problem.

**Zasady projektowe** (pełne uzasadnienie architektury w [Analiza.MD](Analiza.MD)):
- 💬 Reaktywny — Bibo odpowiada na Ciebie, zero crona w tle
- 🧠 Minimalna pamięć — pamięta Twoje imię, cel i język. Nic więcej nie przetrwa między sesjami.
- 🎭 Stały charakter — bez ewoluujących cech, bez dryfu
- 🤔 Krytyczne myślenie — kwestionuje konstruktywnie zamiast potakiwać (skill sokratejskich pytań, ładowany na żądanie)
- 🫧 Podpis: każda wiadomość kończy się `,bibo`
- 📱 Telegram, przez wbudowany gateway Hermesa

## Status

🚧 **Aktywny rebuild, świeżo zbudowany, jeszcze niezwalidowany na żywej instalacji Hermesa.** Poprzednia architektura oparta o cron, specyficzna dla ADHD (v1.3), została w całości wycofana. Pełny plan, wszystkie 24 decyzje i walidacja przeciw 14 warstwom tutoriala Hermesa w [Analiza.MD](Analiza.MD).

## Struktura

```
bibo/
├── SOUL.md                  # Tożsamość — kim jest Bibo, styl, format
├── AGENTS.md                # Reguły pracy — onboarding, trigger krytycznego myślenia, anti-sycophancy
├── brain.template.json      # Minimalny trwały stan (imię, cel, język)
├── skills/
│   └── bibo-critical-thinking/
│       ├── SKILL.md              # Warunki ładowania
│       ├── socratic-questions.md # 5 typów pytań
│       └── examples.md           # Przykładowe rozmowy
└── config.yaml                # Model, fallback, gateway, cron (pusty — Bibo jest reaktywny)
```

## Instalacja

Wymaga działającej instalacji [Hermesa](https://github.com/NousResearch/hermes) (`hermes doctor` powinien być zielony zanim zaczniesz).

**Opcja A — jeśli Twoja wersja Hermesa wspiera zdalną instalację profilu:**
```bash
hermes profile install github.com/Grandpa1001/hi-bibo
```

**Opcja B — manualna (działa z każdą wersją Hermesa):**
```bash
git clone https://github.com/Grandpa1001/hi-bibo.git
hermes profile create bibo --no-skills --description "Bibo — partner do myślenia"
cp -r hi-bibo/bibo/* "$HERMES_HOME/profiles/bibo/"   # dopasuj HERMES_HOME do swojej instalacji
```

Następnie ustaw wymagane zmienne środowiskowe w `.env` profilu (albo przez `hermes secrets`):

```
TELEGRAM_BOT_TOKEN=<token od @BotFather>
TELEGRAM_ALLOWED_USERS=<Twoje Telegram user ID>
ANTHROPIC_API_KEY=<Twój klucz>
```

Zweryfikuj i uruchom:
```bash
hermes doctor
hermes gateway start --profile bibo
```

`config.yaml` ma domyślnie `prompt_cache: true`, model główny `claude-sonnet-4-6` z fallbackiem `claude-haiku-4-5-20251001`, zero pluginów i pusty cron (Bibo tylko odpowiada — nie odpytuje w tle). Nic z tego nie zostało jeszcze uruchomione na żywym Hermesie — jeśli coś nie zgadza się z dokładnym schematem konfiguracji Twojej wersji, to jest oczekiwane na tym etapie; zgłoś issue z tym co znalazłeś.

## Pierwszy kontakt

Bibo nie ma kreatora onboardingowego — sama pierwsza wymiana wiadomości JEST onboardingiem, zgodnie z `AGENTS.md`:
1. Bibo pyta o Twoje imię.
2. Bibo pyta nad czym chcesz pomyśleć, albo z czym się zmagasz.
3. To wszystko — brak dalszych pytań konfiguracyjnych. Bibo zapamiętuje imię, cel i język; nic więcej nie przetrwa.

## Rozwiązywanie problemów

- `hermes doctor` — sprawdza samą instalację
- `hermes prompt-size` — pokazuje stały narzut promptu (SOUL + AGENTS); powinien zostać wyraźnie poniżej 2k tokenów wg celów z [Analiza.MD](Analiza.MD)
- Jeśli Bibo nie ładuje skilla `bibo-critical-thinking` gdy się tego spodziewasz, sprawdź warunki ładowania w `skills/bibo-critical-thinking/SKILL.md` — ma milczeć przy small talk

## Utrzymanie w dobrej kondycji

Po instalacji patrz [MAINTENANCE.pl.md](MAINTENANCE.pl.md) po cykliczną
checklistę — cotygodniowy `hermes doctor`, comiesięczne sprawdzenie kosztów
i bezpieczeństwa, kwartalne restore drille. To bieżące utrzymanie; ten
README pokrywa tylko start.

## Współtworzenie

To repo jest odbudowywane publicznie, iteracyjnie — patrz [Analiza.MD](Analiza.MD) po roadmapę i otwarte milestones. Issues i PR mile widziane, zwłaszcza raporty co się psuje na prawdziwych instalacjach Hermesa.

## Licencja

Patrz [LICENSE](LICENSE).
