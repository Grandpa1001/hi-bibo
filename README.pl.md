[🇬🇧 English](README.md) | 🇵🇱 Polski

# Hi-Bibo 🫧
<img width="241" height="237" alt="1789408829285" src="https://github.com/user-attachments/assets/d7844c83-35dd-4be1-8a56-99133273befa" />

**Bibo to partner obok Ciebie, który kuma ADHD.** Rozmawia z Tobą na
Telegramie, zapamiętuje, jak działasz, i kilka razy dziennie sam się odzywa —
jak kumpel przy biurku, a nie aplikacja z przypomnieniami.

Działa na [Hermes Agent](https://github.com/NousResearch/hermes-agent) — instalator robi z Hermesa na serwerze Bibo.

- 🧠 **Pamięta Cię** — imię, cele, jak u Ciebie wygląda ADHD, co działa, co obiecałeś i kiedy
- 💬 **Sam zaczyna rozmowę** — 1–3 razy dziennie, w ludzkich godzinach, nie gdy właśnie piszesz
- 🧩 **Kuma ADHD** — najmniejszy krok zamiast „weź się w garść”, body doubling, bez moralizowania
- 🪞 **Nie potakuje** — zadaje jedno dobre pytanie zamiast „super pomysł!”
- 💸 **Lekki** — ~13 KB promptu na wiadomość (domyślny Hermes: ~50–60 KB), historia zwijana, zero zbędnych narzędzi
- 🫧 Każda wiadomość kończy się `,bibo`

> Status: **MVP (v0.2)** — zweryfikowane lokalnie (instalacja, prompt, cron), czeka na test na żywym bocie.
> Dlaczego tak, a nie inaczej: [docs/REANALIZA.md](docs/REANALIZA.md).

## Instalacja

Potrzebujesz: serwera/komputera z [Hermes Agent](https://github.com/NousResearch/hermes-agent) ≥ 0.21,
bota Telegram (od [@BotFather](https://t.me/BotFather)), swojego user ID
(od [@userinfobot](https://t.me/userinfobot)) i klucza API Anthropic.

```bash
git clone https://github.com/Grandpa1001/hi-bibo
cd hi-bibo
./install.sh
```

Bibo zostaje **głównym profilem Hermesa** — bez `-p bibo`. Wszystko, co
ustawisz w panelu, przez `/login` czy `hermes model`, trafia prosto do Bibo.
Dlatego najlepiej instalować go na osobnym Hermesie (np. osobny kontener).

Instalator: wgrywa `SOUL.md` i skrypt pulsu, odchudza konfigurację (tylko
nasze klucze — reszta `config.yaml` zostaje), usuwa wbudowane skille, pyta
o token bota, Twoje ID i model, tworzy zadanie „pulsu” i restartuje gateway.
Możesz go uruchamiać ponownie (np. po `git pull`) — pamięć, historia,
logowanie i tokeny zostają.

Wyłączenie Bibo (dane zostają): `./uninstall.sh`. Diagnostyka do wklejenia
w zgłoszeniu (bez sekretów): `./doctor.sh`.

Potem po prostu napisz do swojego bota. Bibo sam Cię pozna.

### Model i koszty

| Opcja | Ustawienie | Uwagi |
|-------|-----------|-------|
| **Klucz API Anthropic** (zalecane) | `ANTHROPIC_API_KEY` w `.env` | Płacisz za tokeny. Przy tym profilu: rząd kilku $ / mies. |
| Konto Claude (OAuth) | `hermes model` albo `/login` (logowanie + wybór modelu) | Wg dokumentacji Hermesa: **tylko Claude Max**, zużywa wyłącznie dokupione *extra usage* — nie limit z planu. |

Domyślny model: `claude-sonnet-5`. Taniej: `hermes config set model.default claude-haiku-4-5`.
Zużycie sprawdzisz: `hermes insights`.

## Panel konfiguracyjny

Hermes ma wbudowany panel webowy (klucze, model, Telegram, cron, pamięć, logi):

```bash
hermes dashboard
```

Na serwerze: `ssh -L 9119:127.0.0.1:9119 twój-serwer`, tam `hermes dashboard --no-open`,
a u siebie otwórz http://127.0.0.1:9119.

## Proaktywne wiadomości

Zadanie `bibo-pulse` budzi się co godzinę, ale model odpala tylko wtedy,
gdy darmowy skrypt `scripts/bibo_pulse.py` uzna, że to dobry moment.
Domyślnie: 8:00–22:00, max 3 dziennie, co najmniej 3 h odstępu, nie w trakcie
Twojej rozmowy. Zmienisz to w `~/.hermes/local/bibo_pulse.json`:

```json
{ "quiet_from": 23, "quiet_to": 9, "max_per_day": 2, "timezone": "Europe/Warsaw" }
```

Wyłączenie: `hermes cron pause bibo-pulse`.

## Co Bibo o Tobie wie

Wszystko, co zapamiętał, jest w dwóch zwykłych plikach na Twoim serwerze:

```bash
cat ~/.hermes/memories/USER.md     # kim jesteś
cat ~/.hermes/memories/MEMORY.md   # obietnice, wzorce, wątki
```

Możesz je edytować. Nigdy nie trafiają do repozytorium. Treść rozmów
przechodzi przez dostawcę modelu (Anthropic).

## Struktura

```
SOUL.md                 # kim jest Bibo: styl, ADHD, pamięć, zaczepki, bezpieczeństwo
config.yaml             # 1 narzędzie, kompresja historii, cache, puls — każda linia skomentowana
scripts/bibo_pulse.py   # bramka proaktywnych wiadomości (0 tokenów)
distribution.yaml       # manifest paczki Hermesa
.no-bundled-skills      # blokuje ~80 wbudowanych skilli Hermesa
.env.template           # jakie sekrety są potrzebne
install.sh              # instalator: Bibo jako główny profil Hermesa
uninstall.sh            # wyłącza Bibo (pamięć zostaje)
doctor.sh               # diagnostyka do wklejenia, bez sekretów
docs/REANALIZA.md       # analiza: co było źle, co i dlaczego zmieniono
```

## Rozwiązywanie problemów

- `hermes prompt-size --platform telegram` — powinno być ~13 KB łącznie. Dużo więcej? Sprawdź, czy `platform_toolsets.telegram` to `[memory]`.
- `hermes cron list` i `hermes cron doctor` — czy puls żyje.
- `hermes logs` — co się dzieje w gatewayu.
- Bibo „zapomina”: sprawdź `memories/USER.md`. Pamięć wczytuje się na starcie sesji — `/new` w czacie zaczyna świeżą sesję z aktualną pamięcią.

## Licencja

MIT — patrz [LICENSE](LICENSE).
