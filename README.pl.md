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

Korzeń repo **jest** dystrybucją profilu Hermes — `distribution.yaml`
leży obok właściwych plików profilu, dokładnie tak jak oczekuje
`hermes profile install`.

```
distribution.yaml          # Manifest: name, version, description, author
SOUL.md                     # Tożsamość — kim jest Bibo, styl, format
AGENTS.md                   # Reguły pracy — onboarding, trigger krytycznego myślenia, anti-sycophancy
brain.template.json         # Minimalny trwały stan (imię, cel, język)
skills/
└── bibo-critical-thinking/
    ├── SKILL.md              # Warunki ładowania
    ├── socratic-questions.md # 5 typów pytań
    └── examples.md           # Przykładowe rozmowy
config.yaml                  # Model główny — minimalny, tylko potwierdzone klucze
```

Reszta plików w korzeniu (`README.md`, `Analiza.MD`, `MAINTENANCE.md`,
`CHANGELOG.md`, `LICENSE`) to dokumentacja projektu, nie treść profilu —
Hermes je ignoruje, ale kopiuje razem z profilem przy instalacji, bo cały
repo jest dystrybucją.

## Instalacja

Wymaga działającej instalacji [Hermes Agent](https://github.com/NousResearch/hermes-agent) (`hermes doctor` powinien być zielony zanim zaczniesz).

```bash
hermes profile install github.com/Grandpa1001/hi-bibo
```

Jeśli reinstalujesz po wcześniejszej nieudanej próbie, dodaj `--force`
(zachowuje dane usera już w profilu):
```bash
hermes profile install github.com/Grandpa1001/hi-bibo --force
```

Zweryfikuj że profil faktycznie się zarejestrował — powinien pojawić się
na liście, nie tylko istnieć jako pliki na dysku:
```bash
hermes profile list
```

Jeśli mimo komunikatu sukcesu profil się nie pojawi — trafiliśmy na
dokładnie ten bug podczas developmentu (pełna diagnoza w
[Analiza.MD](Analiza.MD)). Nasz wcześniejszy `config.yaml` używał
zmyślonego schematu, który najpewniej wywalał wewnętrzną walidację
Hermesa i po cichu blokował rejestrację. Aktualny `config.yaml` używa
tylko kluczy potwierdzonych w
[prawdziwej dokumentacji konfiguracji Hermesa](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/configuration.md).
Jeśli nadal to się powtórzy — zgłoś issue.

Ustaw wymagane zmienne środowiskowe — wg
[dokumentacji Telegrama Hermesa](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/telegram.md)
idą do `~/.hermes/.env` (globalnie), chyba że Twoja instalacja ma inny
`HERMES_HOME`:

```
TELEGRAM_BOT_TOKEN=<token od @BotFather>
TELEGRAM_ALLOWED_USERS=<Twoje Telegram user ID>
ANTHROPIC_API_KEY=<Twój klucz>
```

Przetestuj w CLI:
```bash
hermes -p bibo chat
```

Potem skonfiguruj gateway Telegram — albo interaktywny kreator (sam
tworzy bota i wykrywa Twoje user ID):
```bash
hermes gateway setup
```
albo, jeśli masz już token bota i user ID ustawione jak wyżej:
```bash
hermes -p bibo gateway
```

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
