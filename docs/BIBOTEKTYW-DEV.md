# Bibotektyw — plan developmentu

> Status: **zamknięty** — decyzje ostateczne, wątpliwości rozstrzygnięte. Wrzesień 2026.
> Ekrany, design i prompty: załączniki A–D na końcu pliku.
> Jak wygląda: [prototyp/bibotektyw.html](prototyp/bibotektyw.html).
> Ten plik: **jak to zbudować**. Jedyna rzecz do potwierdzenia na żywo to spike M0 (§6).

---

## 1. Decyzje ostateczne

| Obszar | Decyzja |
|--------|---------|
| Forma | Telegram Mini App (pełny ekran), czat tylko do propozycji, karty wyniku i kontroli |
| Dystrybucja | **Każdy user ma własną Mini App**: własny bot → własny Hermes → wtyczka `bibo-tryby` serwuje front i API. Brak centralnego serwera |
| HTTPS | **Tylko Cloudflare quick tunnel** (`cloudflared`, bez konta, bez domeny, bez otwierania portów). Adres zmienia się po restarcie — wtyczka sama przestawia przycisk menu |
| Komponent | Wtyczka `bibo-tryby` (Python) + frontend `miniapp/` (Preact + Vite + TS), `miniapp/dist` commitowany |
| Model gry | 2 × Haiku (`claude-haiku-4-5`) na sprawę, odpowiedź JSON, walidacja, 1 ponowienie, bank zapasowy |
| Powrót do czatu | Karta wyniku (`sendPhoto` + efekt) + komentarz Bibo (wiadomość wewnętrzna do sesji, 1 × Sonnet) |
| Przyciski w czacie | Tylko `web_app` — zero callbacków, zero prywatnego API Hermesa |
| „🐢 Jeszcze nie” | Bibo pyta, co blokuje (prompt §C.6) |
| Dane | JSON w `$HERMES_HOME/local/bibo_tryby/` — przeżywają aktualizacje i reinstalację |
| Wyłączenie | `hermes plugins disable bibo-tryby` → Bibo działa dokładnie jak przed instalacją |
| Styl | Style guide Bibo: Roboto, `#000/#FFF/#F2F2F2/#009688`, pozy postaci (§B) |

## 2. Rozstrzygnięte wątki

| Wątek | Rozstrzygnięcie |
|-------|-----------------|
| Jedna aplikacja dla wszystkich userów? | Nie. Przyciski `web_app` przyjmują dowolny HTTPS, więc każdy bot wskazuje na swój tunel. `initData` podpisuje token danego bota — weryfikuje je tylko jego instalacja. BotFather `/newapp` niepotrzebne |
| Domena / certyfikat | Niepotrzebne. `cloudflared tunnel --url http://127.0.0.1:8787` daje `https://*.trycloudflare.com` z certyfikatem Cloudflare |
| Zmienny adres tunelu | Wtyczka odczytuje adres z wyjścia `cloudflared` i wywołuje `setChatMenuButton`. Wiadomości wysyłane później mają aktualny adres. Stare przyciski w historii czatu po restarcie nie działają — wejście zawsze przez `🎲 Tryby` (znane ograniczenie, §10) |
| Szkic wymówki a zmiana adresu | `CloudStorage` jest przypisane do bota, nie do adresu → szkic przetrwa. Nie używamy `localStorage` |
| Docker | `cloudflared` działa **w tym samym kontenerze** co Hermes (binarka w `$HERMES_HOME/bin`, na wolumenie) → nie trzeba publikować portów ani zmieniać compose |
| Konflikt z `bibo-podpis` | Hook `transform_llm_output` bierze **pierwszą** podmianę tekstu — dwie wtyczki by się wykluczały. Dlatego: `bibo-tryby` wykrywa znacznik w `post_llm_call` (tylko obserwuje), a **`bibo-podpis` usuwa znaczniki `[[…]]`** przed podpisem (jedna mała zmiana, §5) |
| Kliknięcia przycisków w czacie | Nie ma ich: propozycja ma jeden przycisk `web_app` (brak reakcji = „nie dziś”), kontrola otwiera ekran w Mini App |
| `sendData` z Mini App | Nie używamy (Hermes ignoruje `web_app_data`). Wszystko idzie przez API wtyczki |
| Wysyłka do Telegrama z wtyczki | Bezpośrednio przez Bot API (HTTPS, token z `.env`), **nie** przez prywatne `adapter._bot`. Wysyłanie nie koliduje z pollingiem Hermesa |
| Komentarz Bibo po sprawie | `adapter.handle_message(MessageEvent(..., internal=True))` na pętli gatewaya — mechanizm, którym Hermes sam budzi sesje. Gdy brak referencji do gatewaya (np. restart i jeszcze żadnej wiadomości) → **fallback**: notatka o sprawie trafia do następnej tury Bibo przez `pre_llm_call`. Karta idzie zawsze |
| Start usług po restarcie | Wtyczka startuje usługi (API, tunel, kontrola) we **własnym wątku z własną pętlą** zaraz po załadowaniu w procesie gatewaya — nie czeka na pierwszą wiadomość. Wykrycie procesu gatewaya: M0.2 |
| Kontrola po restarcie | Termin w `sprawy.json`, pętla co 60 s → przeżywa restart |
| Model Haiku bez nowego klucza | `ctx.register_auxiliary_task("bibo_tryby", defaults=…)` + `call_llm(task="bibo_tryby")` — korzysta z logowania Hermesa, nadpisywalne w `auxiliary.bibo_tryby` |
| Bezpieczeństwo publicznego adresu | API na `127.0.0.1`, świat widzi je tylko przez tunel; każde żądanie z ważnym `initData` (≤ 1 h) od usera z `TELEGRAM_ALLOWED_USERS`; limity |
| Node na serwerze | Niepotrzebny — `dist/` jest w repo |

---

## 3. Architektura

```
                      ┌──────────────── proces gatewaya Hermesa ────────────────┐
Telegram ◄──polling── │ pętla gatewaya                                          │
  ▲   ▲               │   Bibo (Sonnet) ◄─ hooki: pre_llm_call / post_llm_call  │
  │   │               │        ▲                   pre_gateway_dispatch (ref.)  │
  │   │               │        └─ MessageEvent(internal=True)  ◄──────────┐     │
  │   │               │                                                   │     │
  │   │ Bot API       │ wątek „usługi” (własna pętla asyncio)             │     │
  │   └───────────────┤   api.py   127.0.0.1:8787  ── Haiku (call_llm) ───┘     │
  │                   │   tunel.py cloudflared (proces potomny)                 │
  │                   │   kontrola.py (co 60 s)                                 │
  │                   └──────────────────────┬──────────────────────────────────┘
  │                                          │ https://*.trycloudflare.com
  └──── Mini App (Preact, w Telegramie) ─────┘
```

Zasada: **pętla gatewaya dotykana tylko w dwóch miejscach** — synchroniczne hooki
(szybkie, bez I/O) i wstrzyknięcie wiadomości wewnętrznej
(`asyncio.run_coroutine_threadsafe`). Cała reszta żyje w wątku usług; jego awaria
nie wpływa na Bibo.

---

## 4. Struktura repo (nowe pliki)

```
plugins/bibo-tryby/
  plugin.yaml
  __init__.py      # register(ctx): zadanie auxiliary, hooki, komendy, start wątku usług
  uslugi.py        # wątek z pętlą: start/stop API, tunelu, kontroli; referencje do gatewaya
  wystawienie.py   # interfejs Wystawienie + QuickTunnel (cloudflared); url_staly = pomija tunel
  telegram.py      # klient Bot API (httpx): sendMessage, sendPhoto, setChatMenuButton
  api.py           # aiohttp: /api/*, /health, statyka z static/
  auth.py          # initData, lista userów, limity
  magazyn.py       # JSON atomowo: ustawienia, kartoteka, sprawy
  llm.py           # call_llm → JSON → walidacja → ponowienie → bank
  czat.py          # propozycja, karta wyniku, wiadomości wewnętrzne, fallback notatki
  kontrola.py      # terminy kontroli
  tryby/__init__.py, tryby/detektyw.py   # prompty §C, bank, podejrzani startowi
  sucho.py         # test promptów z terminala
  static/          # ← miniapp/dist kopiowane przez install.sh (nie w repo)
miniapp/           # Preact + Vite + TS; src/{main.tsx,tg.ts,api.ts,stan.ts,ekrany/,ui/,styl.css}
  public/postaci/, public/karty/     # pozy (PNG 2×) i 3 karty wyniku 1200×630
  dist/            # build, commitowany
tests/bibo_tryby/  # test_auth, test_llm, test_magazyn, test_api, wymowki.yaml
```

`wystawienie.py` to jedyny punkt, który wie, skąd bierze się adres HTTPS. Dziś ma
jedną implementację (`QuickTunnel`) i jedno obejście (`url_staly` w ustawieniach —
gdy ktoś sam wystawi port, tunel się nie uruchamia). Nic więcej nie budujemy.

---

## 5. Zmiany w istniejących plikach (minimalne)

| Plik | Zmiana | Ryzyko |
|------|--------|--------|
| `plugins/bibo-podpis/__init__.py` | Przed podpisem usuń znaczniki sterujące `\[\[[a-z_:-]+\]\]`; jeśli po usunięciu tekst pusty → `None`. Test: „…tekst [[tryb:detektyw]]” → „…tekst bibo” | Niskie — działa także bez `bibo-tryby` |
| `install.sh` | Nowa sekcja „Tryby (Mini App)” przed „Uruchamiam Bibo” (§7) | Niskie — pytanie T/n, „n” = nic się nie zmienia |
| `doctor.sh` | Sekcja „Tryby”: wtyczka, `/health` lokalnie i przez tunel, proces `cloudflared`, przycisk menu | Brak |
| `uninstall.sh` | Wyłącz i usuń wtyczkę, `static/`, zatrzymaj `cloudflared`; `local/bibo_tryby/` zostaje (jak pamięć) | Niskie |
| `README.md` / `README.pl.md` | Sekcja „Tryby / Mini App”: co to, jak włączyć, prywatność (wymówki idą do Anthropic, kartoteka zostaje na serwerze) | Brak |
| `SOUL.md`, `config.yaml` | **Bez zmian** | — |

---

## 6. Kamienie milowe

### M0 — Spike integracji (½–1 dnia) — jedyna niewiadoma

Minimalna wtyczka, na prawdziwym bocie. Wyniki wpisujemy w §12.

| # | Sprawdzamy | Odbiór | Jeśli nie działa |
|---|-----------|--------|------------------|
| 0.1 | `register_auxiliary_task` + `call_llm(task="bibo_tryby")` | `/bt_ping` → odpowiedź Haiku | `call_llm(provider=…, model=…)` wprost |
| 0.2 | Wykrycie procesu gatewaya w `register()` i start wątku usług | `curl 127.0.0.1:8787/health` po restarcie, bez pisania do bota | start przy pierwszym `pre_gateway_dispatch` (menu i tak ustawia Bot API) |
| 0.3 | `cloudflared` w kontenerze: adres z wyjścia, proces potomny ginie z gatewayem | adres działa z telefonu; brak osieroconych procesów | grupa procesów + `atexit` |
| 0.4 | `setChatMenuButton` + wiadomość z `web_app` i `style` przez Bot API | Mini App otwiera się z menu i z przycisku | bez `style` |
| 0.5 | `MessageEvent(internal=True)` z wątku usług na pętlę gatewaya | Bibo odpowiada w czacie, tura jest w historii | fallback przez `pre_llm_call` (zawsze wdrożony) |
| 0.6 | `post_llm_call` widzi znacznik; `bibo-podpis` go usuwa | propozycja przychodzi, znacznik nie wycieka | — |
| 0.7 | `sendPhoto` + `message_effect_id` | konfetti w czacie | bez efektu |

**Stop:** jeśli 0.2 i jego obejście zawiodą — wracamy do projektowania architektury przed M1.

### M1 — Frontend na sztucznym API (2–3 dni)
Ekrany z prototypu jako komponenty Preact (Start, Zeznanie, Analiza, Przesłuchanie,
Obrady, Werdykt, Kontrola, Kartoteka); `tg.ts` z natywnymi przyciskami, haptyką,
`CloudStorage`, `showPopup`, kolorami nagłówka/tła; tryb mock (`npm run dev`) z atrapą
Telegrama i sztucznym API; routing hash (`#/`, `#/sprawa`, `#/kontrola/<id>`, `#/kartoteka`);
3 karty PNG do `sendPhoto`.
**Odbiór:** przebieg w mocku na telefonie jak w prototypie; `dist/` ≤ 300 KB bez postaci.

**Status: ✅ zrobione (26.09.2026).** `dist/`: kod + fonty 252 KB, postaci 188 KB, karty 576 KB.
Przetestowane w mocku (375×812): start, zeznanie, analiza, przesłuchanie, podpowiedź, werdykt,
przełącznik kontroli, zamknięcie, kontrola, kartoteka, ścieżka błędu z ponowieniem, wejście prosto
na `#/sprawa`; build bez Telegrama pokazuje „Otwórz z czatu z Bibo”.
- Praca nad frontem: `cd miniapp && npm install && npm run dev` (tryb mock włącza się sam; w buildzie: `?mock=1`).
  Atrapa API: wymówka ze słowem „błąd” → błąd modelu; riposta < 12 znaków → werdykt „częściowo”.
- Przed commitem: `npm run build` — `dist/` jest w repo.
- Karty: `python3 miniapp/narzedzia/karty.py --roboto <Roboto.ttf> --mono <RobotoMono.ttf>` (fonty zmienne z google/fonts, poza repo).
- Przyciski natywne deklaruje tylko ekran-liść (`usePrzyciski`) — efekt rodzica nadpisałby dziecko.

### M2 — Prompty i logika trybu (1–2 dni)
`detektyw.py` (prompty §C.1–C.3), `llm.py` (walidacja, ponowienie, bank),
`sucho.py` + `wymowki.yaml` (~15 przypadków: typowe wymówki, prawdziwe zmęczenie,
blokada zewnętrzna, żart, pusty, angielski, prompt injection, bardzo długi).
**Odbiór:** testy zielone; raport na sucho zaakceptowany przez Ciebie; ≥ 90 % JSON
za 1. razem; zmęczenie nigdy „obalona”; injection bez efektu.

### M3 — API i dane (1–2 dni)
`api.py`, `auth.py`, `magazyn.py` wg §8–§9. **Odbiór:** `test_api.py` — pełna sprawa na
podrobionym Haiku; 401/403/409/422/429 zgodnie z kontraktem.

### M4 — Czat, tunel, instalacja (2 dni)
`wystawienie.py`, `telegram.py`, `czat.py`, `kontrola.py`, zmiany z §5.
**Odbiór:** świeża instalacja w Dockerze → „T” w sekcji Tryby → pełna sprawa z telefonu:
propozycja (max 1×/dzień), karta z konfetti, komentarz Bibo, kontrola po 10 min;
restart kontenera → menu działa z nowym adresem; `./doctor.sh` zielony;
`hermes plugins disable bibo-tryby` → brak śladów.

### M5 — Tydzień użytkowania
Liczba spraw, % „ruszyło”, werdykty, trafność propozycji, koszt (`hermes insights`),
uwagi do tonu → poprawki promptów → v1.0.

---

## 7. Instalacja i diagnostyka

**Aktualizacja (od 26.09.2026):** `hermes bibo update` — wtyczka `bibo-cli` pobiera
`update.sh` z GitHuba i uruchamia go. Skrypt pyta API GitHuba o SHA commita `main` — gdy równy
`local/bibo_wersja`, kończy bez pobierania (`--force` wymusza). Inaczej pobiera paczkę tego commita
do katalogu tymczasowego, uruchamia z niej **swoją nową wersję** (`--install <źródło>`) i wgrywa: `SOUL.md` (tylko gdy profil
to Bibo), `scripts/`, wtyczki `bibo-podpis`, `bibo-cli` i — jeśli już zainstalowana —
`bibo-tryby` z `miniapp/dist` jako `static/` (+ `cloudflared`, gdy brak), potem restart gatewaya.
Kopię repo `~/hi-bibo` odświeża tylko, gdy ma do niej prawa (zamiana przez `.nowe`/`.stare`,
bez połowicznego usuwania); w Dockerze `hermes bibo update` działa jako użytkownik `hermes`, więc
root przy każdym zapisie oddaje pliki właścicielowi katalogu Hermesa. Nie rusza `.env`, `config.yaml`, pamięci, cronów. Zmienne do testów: `BIBO_GALAZ`, `BIBO_REPO`, `BIBO_PACZKA`.
Pierwszy raz (bez `bibo-cli`): `curl -fsSL https://raw.githubusercontent.com/Grandpa1001/hi-bibo/main/update.sh | bash`.

**Tryb demo do M3:** wtyczka serwuje front z `static/`; dopóki `API_GOTOWE = False` (api.py),
przycisk menu otwiera `…/?mock=1` — prawdziwy Telegram (natywne przyciski, haptyka), udawane
odpowiedzi, czarny pasek „Tryb demo”. Diagnostyka M0 zostaje pod `/spike`.

**`install.sh` — sekcja „Tryby (Mini App)”:**

```
Tryby Bibo (Mini App z grą Bibotektyw)?
Działa przez darmowy tunel Cloudflare — bez domeny i bez konta. [T/n]
```

1. Pobiera `cloudflared` (oficjalne wydanie z GitHub, wg `uname -m`, sprawdza sumę SHA256) do `$HOME_DIR/bin/`, jeśli nie ma.
2. Kopiuje `plugins/bibo-tryby` i `miniapp/dist` → `plugins/bibo-tryby/static/`; `fix_owner`.
3. Tworzy `local/bibo_tryby/ustawienia.json`, jeśli nie ma (nie nadpisuje).
4. `hermes plugins enable bibo-tryby --no-allow-tool-override`.
5. Restart gatewaya (istniejący krok na końcu skryptu).

„n” → nic nie kopiuje; jeśli wtyczka była włączona — `hermes plugins disable bibo-tryby`.

**`doctor.sh` — sekcja „Tryby”:** wtyczka włączona · `static/index.html` jest ·
`127.0.0.1:8787/health` · proces `cloudflared` żyje · `<url>/health` przez tunel ·
`getChatMenuButton` = aktualny adres · `auxiliary.bibo_tryby` → Haiku.

---

## 8. Kontrakty API

Wspólne: nagłówek `X-Init-Data: <Telegram.WebApp.initData>`, JSON, UTF-8.
Błędy: `{"blad": "<kod>", "komunikat": "<po polsku, dla usera>"}` —
401 `podpis` · 403 `uzytkownik` · 404 `sprawa` · 409 `stan` · 422 `dane` · 429 `limit` · 503 `model`.

```http
GET  /api/hub
→ {"tryby":[{"id":"detektyw","nazwa":"Bibotektyw","opis":"…","aktywny":true}, …],
   "statystyki":{"zamkniete":6,"obalone":4,"najczestszy":{"nazwa":"Perfekcjonista","emoji":"🎩"}},
   "aktywna_sprawa":null}

POST /api/sprawa                                   → 201 {"id":"s_7f3a","numer":7}

POST /api/sprawa/{id}/zeznanie {"wymowka":"…"}     (≤500 zn.)
→ {"podejrzany":{"nazwa":"Perfekcjonista","emoji":"🎩","nowy":false,"zatrzymanie":3,"ostatnio":"2026-09-19"},
   "pytanie":"…?","podpowiedz":"…","zrodlo":"model"|"bank"}

POST /api/sprawa/{id}/riposta {"riposta":"…"} | {"uniewinnienie":true}
→ {"werdykt":"obalona"|"czesciowo"|"uniewinniona","podsumowanie":"…","krok":"…","zrodlo":"model"|"bank"}

POST /api/sprawa/{id}/zamknij {"kontrola_min":10|null}
→ {"ok":true,"kontrola":"2026-09-24T22:02:00+02:00"|null}      (karta → komentarz Bibo; front: close())

GET  /api/sprawa/{id}                                          (ekran kontroli)
→ {"id":"s_7f3a","numer":7,"podejrzany":{"nazwa":"Perfekcjonista","emoji":"🎩"},
   "krok":"…","werdykt":"obalona","kontrola":"2026-09-24T22:02:00+02:00"|null}

POST /api/sprawa/{id}/kontrola {"ruszylo":true|false}          (false → prompt §C.6)
→ {"ok":true}

GET  /api/kartoteka → {"podejrzani":[…], "sprawy":[…]}
GET  /health        → {"ok":true,"wersja":"0.1.0"}              (bez auth, bez adresu, bez danych)
```

Sprawa bez `zamknij` przez 30 min → usuwana, nie trafia do kartoteki. Jedna aktywna sprawa naraz —
`POST /api/sprawa` porzuca poprzednią niezamkniętą (front po przeładowaniu otwiera nową, szkic wymówki wraca z `CloudStorage`).
Błędy: front pokazuje `komunikat` z odpowiedzi; brak pola → własny tekst dla danego `blad`.

## 9. Dane (`$HERMES_HOME/local/bibo_tryby/`)

```jsonc
// ustawienia.json
{"tryby": ["detektyw"], "port": 8787, "url_staly": null,
 "propozycje_dziennie": 1, "kontrola_min": 10, "limit_haiku_na_godzine": 30, "strefa": "Europe/Warsaw"}

// stan_tunelu.json — zapisuje wtyczka
{"url": "https://abc-def.trycloudflare.com", "od": "2026-09-25T08:00:00+02:00"}

// kartoteka.json
{"wersja": 1, "nastepny_numer": 8,
 "podejrzani": {"Perfekcjonista": {"emoji": "🎩", "zatrzymania": 5, "obalone": 4, "ruszylo": 2, "ostatnio": "2026-09-24"}},
 "sprawy": [{"numer": 7, "data": "…", "podejrzany": "Perfekcjonista", "wymowka": "…", "pytanie": "…",
             "riposta": "…", "werdykt": "obalona", "podsumowanie": "…", "krok": "…", "ruszylo": null}],
 "propozycje": {"2026-09-24": 1},
 "notatka_dla_bibo": null}          // fallback komentarza (§2), czyszczona po użyciu

// sprawy.json — aktywne i czekające na kontrolę
{"s_7f3a": {"numer": 7, "user": 123456, "etap": "zamknieta", "ostatnia_akcja": "…",
            "kontrola": "2026-09-24T22:02:00+02:00", "kontrola_wyslana": false}}
```

Podejrzani startowi: Perfekcjonista 🎩 · Jutrzejszy Ja 📅 · Research Bez Dna 🔎 · Brak Paliwa 🔋 · Mgła Startowa 🌫️.
Nowych dodaje Haiku #1 (`nowy: true`), maks. 20.

## 10. Bezpieczeństwo i znane ograniczenia

```python
def weryfikuj_init_data(raw: str, token: str, max_wiek: int = 3600) -> dict:
    pola = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=True))
    podany = pola.pop("hash", "")
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(pola.items()))      # wszystkie pola poza hash
    sekret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    if not podany or not hmac.compare_digest(hmac.new(sekret, dcs.encode(), hashlib.sha256).hexdigest(), podany):
        raise BladAuth("podpis")
    if time.time() - int(pola.get("auth_date", 0)) > max_wiek:
        raise BladAuth("podpis")
    return json.loads(pola["user"])
```

- `user.id` ∈ `TELEGRAM_ALLOWED_USERS`; limity: 30 × Haiku/h, body ≤ 4 KB, 1 aktywna sprawa.
- Haiku bez narzędzi; tekst usera w tagach i escapowany; przyjmujemy tylko JSON wg schematu.
- Do czatu i sesji Bibo trafia tylko treść po walidacji; HTML escapowany w podpisach.
- CSP: skrypty `self` + `telegram.org`; `nosniff`; logi bez treści wymówek.

**Znane ograniczenia (świadomie akceptowane):**
- Quick tunnel nie ma SLA i jest deklarowany jako narzędzie testowe; limit 200 równoległych żądań (dla jednej osoby bez znaczenia).
- Po restarcie adres się zmienia → stare przyciski w historii czatu nie działają; menu `🎲 Tryby` zawsze aktualne.
- Gdy Cloudflare nie wystawi tunelu — tryby są chwilowo niedostępne, Bibo działa normalnie; `tunel.py` ponawia z backoffem.

## 11. Testy i definicja „gotowe”

| Poziom | Co |
|--------|----|
| Jednostkowe (`pytest`) | initData (poprawny / zmieniony / stary / bez hash), walidacja JSON Haiku, bank, zapis atomowy, limity, usuwanie znaczników w `bibo-podpis` |
| API (`aiohttp` test client) | pełna sprawa na podrobionym Haiku, kody błędów, wygaśnięcie, kontrola |
| Prompty | `sucho.py` na `wymowki.yaml`, przegląd raportu |
| Front | tryb mock na telefonie (375×812) |
| E2E (ręcznie) | propozycja → sprawa → karta → komentarz → kontrola → kartoteka; restart kontenera; wyłączenie wtyczki |

**Gotowe (MVP):**
- [ ] Sprawa od propozycji do komentarza Bibo działa na telefonie w ≤ 2 min.
- [ ] 2 × Haiku + 1 × Sonnet na sprawę; koszt w `hermes insights` zgodny z szacunkiem.
- [ ] Propozycja maks. 1×/dzień; znacznik nigdy nie wycieka.
- [ ] Kontrola po 10 min, także po restarcie.
- [ ] Restart kontenera → menu działa z nowym adresem bez ręcznych kroków.
- [ ] `hermes plugins disable bibo-tryby` → Bibo jak przed instalacją.
- [ ] `./install.sh` (T i n) idempotentny; `./doctor.sh` zielony; testy zielone; README uzupełnione.

## 12. Wyniki spike'u M0

**Wynik: M0 zaliczony (25.09.2026).** Hermes 0.21 w Dockerze (VPS), wtyczka `bibo-tryby` 0.0.1.
Wszystkie testy ze strony diagnostycznej zwróciły 200, a karta, przycisk i odpowiedź Bibo pokazały się w czacie.

| # | Wynik | Jak zrobione (do użycia w M1–M4) |
|---|-------|----------------------------------|
| 0.1 | ✅ | `register_auxiliary_task("bibo_tryby", defaults={provider, model})` + `call_llm(task=…)` w `run_in_executor` |
| 0.2 | ✅ | `_HERMES_GATEWAY == "1"` **i** `gateway.status.get_running_pid() == os.getpid()` (ten sam test co Hermes); wątek startowy czeka do 180 s — usługi ruszają bez pierwszej wiadomości |
| 0.3 | ✅ | `cloudflared` z `$HERMES_HOME/bin`, `start_new_session=True`, adres regexem z stderr, restart z backoffem 5 → 300 s |
| 0.4 | ✅ | Bot API bezpośrednio (`aiohttp`), `setChatMenuButton` bez `chat_id` = dla wszystkich czatów prywatnych; `style` z fallbackiem bez niego |
| 0.5 | ✅ | `gateway.run._gateway_runner_ref()` → `runner._gateway_loop` + `runner.adapters[Platform.TELEGRAM]`; `run_coroutine_threadsafe(adapter.handle_message(MessageEvent(internal=True)))`; źródło: zapamiętane z `pre_gateway_dispatch` albo `SessionSource(dm)` z user id; fallback `notatki.json` → `pre_llm_call` |
| 0.6 | ✅ częściowo | `bibo-podpis` usuwa `[[nazwa:wartosc]]` (testy jednostkowe); wykrycie w `post_llm_call` gotowe — pełny test z instrukcją propozycji w M4 |
| 0.7 | ✅ | `sendPhoto` multipart + `message_effect_id` `5046509860389126442` (🎉), fallback bez efektu |

Dodatkowo: obie wtyczki deklarują `provides_hooks` i przechodzą `hermes plugins validate`
(ostrzeżenie `tunnel_service` jest oczekiwane). Testy: `python -m unittest discover -s tests/bibo_tryby`.
Instalacja ręczna na VPS (do czasu M4): paczka `main.tar.gz` z GitHuba zamiast `git pull` — katalog w kontenerze nie jest repozytorium.

## 13. Poza MVP (bez projektowania teraz)

Kolejne tryby („Misja 10 minut”, „Zrzut z głowy”) · puls ze „starą sprawą” · stały adres
(własna domena / Tailscale Funnel — wystarczy nowa implementacja w `wystawienie.py` albo `url_staly`) ·
`addToHomeScreen` · kartoteka jako rich message · eksport kartoteki · wersja EN ·
docelowe eksporty postaci (przezroczyste PNG/SVG 2×/3×) — do tego czasu wycinki z prototypu.

---

# Załączniki

## A. Przebieg sprawy (ekrany)

```
CZAT                     MINI APP                                                         CZAT
propozycja ─Otwieramy─►  Start ─► Zeznanie ─► [Haiku #1] ─► Przesłuchanie ─► [Haiku #2] ─► Werdykt ─► karta wyniku
    │                        │                                        ├─ 💡 Podpowiedź (0 tok.)              └─ ⏰ kontrola za 10 min
 (brak reakcji            Kartoteka                                   └─ 🟢 Ona ma rację ─► [Haiku #2, uniewinnienie]
```

| Ekran | Co widzisz | Kto generuje | Telegram API |
|-------|-----------|--------------|--------------|
| **0. Propozycja** (czat) | „🕵️ Brzmi jak klasyczny zator. Otwieramy śledztwo?” `[🔍 Otwieramy]` (brak reakcji = „nie dziś”) | decyzja „czy”: Bibo; treść: kod | `InlineKeyboardButton.web_app`, `style: success` |
| **1. Start** | Bibo-detektyw i „Dobry wieczór, detektywie.”; kafle trybów z pozami Bibo, statystyki, kartoteka | kod | `themeParams`, `SecondaryButton` |
| **2. Zeznanie** | Bibo w pozie „Skupienie” z dymkiem: „Na krześle siedzi wymówka, nie Ty…”; karta „Sprawa #7” z polem na wymówkę | kod | `MainButton` „Złóż zeznanie”, `CloudStorage` (szkic), haptyka lekka |
| **3. Analiza** | Bibo „Zastanawianie” z dymkiem myśli, „Analizuję zeznanie” | Haiku #1 | `MainButton.showProgress()` |
| **4. Przesłuchanie** | Karta podejrzanego (emoji na tle miarki, nr, zatrzymania), cytat wymówki; Bibo-detektyw z dymkiem pytania; pole riposty, `💡 Podpowiedź`, `🟢 Ona ma rację` | karta: kod; pytanie i podpowiedź: Haiku #1 | `showPopup` (podpowiedź), `MainButton` „Odpowiedz” |
| **5. Obrady** | Bibo-detektyw z dymkiem myśli, „Sąd obraduje” | Haiku #2 | `MainButton.showProgress()` |
| **6. Werdykt** | Bibo „Radość & Sukces” wskakuje, turkusowa pieczątka; karta „Werdykt”; turkusowa karta „👣 Pierwszy krok” z pozą „Działanie & Ruch” | animacja: kod; treść: Haiku #2 | `HapticFeedback.notificationOccurred('success')`, `MainButton` „Zamknij akta i wróć do Bibo”, `SecondaryButton` „⏰ Zajrzyj za 10 min” |
| **7. Powrót** (czat) | Karta wyniku jako zdjęcie z podpisem (poza zależna od werdyktu), konfetti | kod | `sendPhoto` + `message_effect_id` (🎉) |
| **Kartoteka** | Teczki z komiksowym konturem i turkusowymi pinezkami, kwadraty zatrzymań/obaleń; Bibo-detektyw w nagłówku | kod | — |
| **Kontrola** (czat → Mini App) | W czacie: „🕵️ Kontrola po sprawie #7: ruszyło z „…”?” `[📁 Otwórz akta]`. W Mini App: Bibo „Działanie & Ruch”, `[✅ Ruszyło]` `[🐢 Jeszcze nie]` | kod; „Jeszcze nie” → Bibo pyta, co blokuje | `web_app`, `close()` |

Werdykt → efekty:

| Werdykt | Pieczątka · postać | Haptyka | Efekt karty w czacie |
|---------|-----------|---------|----------------------|
| 💥 obalona | OBALONA, turkus · Bibo „Radość & Sukces” | `success` | 🎉 |
| ⚖️ częściowo | CZĘŚCIOWO, czerń · Bibo „Zastanawianie” | `warning` | — |
| 🟢 uniewinniona | UNIEWINNIONA, czerń · Bibo „Skupienie” | `success` (miękko) | ❤️ |

Zasady interakcji: bez licznika; zawsze wyjście (`✕ Zamknij` w nagłówku,
potwierdzenie zamknięcia tylko gdy jest niewysłany tekst —
`enableClosingConfirmation`); przerwana sprawa wygasa po 30 min i nie trafia do kartoteki.

---

## B. Design

Źródło: style guide Bibo — [`prototyp/assets/style-guide.jpg`](prototyp/assets/style-guide.jpg).

### Koncepcja

**Bibo prowadzi śledztwo.** Maskotka Bibo (puchata postać ze słuchawkami
i tabletem, czarno-biała kreska) jest Twoim partnerem-detektywem i w każdym
ekranie pokazuje emocję chwili pozą ze style guide'u. Interfejs mówi tym
samym językiem co rysunek: biało-szare tło, **grube czarne kontury 2 px**,
komiksowe cienie przesunięte o 4 px, dymki jak w komiksie, turkus jako
jedyny kolor. Motyw kryminalny niosą detale: numer sprawy, zdjęcie z miarką
wzrostu, cytat zeznania, pieczątka werdyktu, teczki na pinezkach. Całą
odwagę wydajemy na **jeden moment — Bibo wskakuje z radości, a pieczątka
wbija się w akta**.

### Postać — pozy na ekranach

| Poza (style guide) | Plik | Gdzie |
|--------------------|------|-------|
| Główny logotyp | `logo.png` | avatar bota w czacie, ikona Mini App, nagłówek |
| Śledztwo & Odkrycie | `detektyw.png` | start (hub), pytanie śledczego, obrady, kartoteka, ikona trybu Bibotektyw |
| Skupienie | `skupienie.png` | zeznanie („Bibo słucha”), werdykt „uniewinniona”, ikona „Zrzut z głowy” |
| Zastanawianie | `mysli.png` | analiza (Haiku #1), werdykt „częściowo” |
| Radość & Sukces | `radosc.png` | werdykt „obalona”, karta wyniku w czacie |
| Działanie & Ruch | `ruch.png` | karta „Pierwszy krok”, ikona „Misja 10 minut” |

Pliki w prototypie są wycięte z jednego obrazu style guide'u (opaque, białe
tło, łączone z tłem przez `mix-blend-mode: multiply`). **Do wdrożenia
potrzebne są osobne eksporty** — PNG/SVG z przezroczystym tłem, 2× i 3×,
bez resztek sąsiednich postaci (np. w „Radość” palec prawej ręki jest przycięty).

### Kolory

| Token | Hex | Rola |
|-------|-----|------|
| `--black` | `#000000` | kontury, tekst nagłówków, komiksowe cienie, znacznik „zatrzymanie” |
| `--white` | `#FFFFFF` | karty, dymki, pola tekstowe |
| `--grey` | `#F2F2F2` | tło Mini App (szary pomocniczy) |
| `--teal` | `#009688` | **akcent**: przycisk główny, H1/H2, pieczątka, karta kroku, pinezki |
| `--teal-h` / `--teal-a` | `#00897B` / `#00796B` | przycisk główny: najechany / aktywny |
| `--teal-50` / `--teal-100` | `#E0F2F1` / `#B2DFDB` | przycisk drugorzędny: aktywny / najechany, pigułki, tło karty wyniku |
| `--muted` | `#5E5E5E` | tekst pomocniczy |

Jeden jasny świat niezależnie od motywu Telegrama — postać jest czarno-biała
i na ciemnym tle traci czytelność. Ustawiamy `setHeaderColor('#FFFFFF')`,
`setBackgroundColor('#F2F2F2')`, `setBottomBarColor('#FFFFFF')`,
`MainButton.setParams({color:'#009688'})`.

### Typografia

| Rola | Krój | Użycie |
|------|------|--------|
| Nagłówki | **Roboto** 700 (H2) / 900 (hub, pieczątka) | H1/H2 w turkusie (jak w guide), powitanie „Dobry wieczór, detektywie.” czerń + turkus |
| Tekst | **Roboto** 400/500 | treść, dymki (500), pola |
| Akta | **Roboto Mono** 500/700 | numer sprawy, daty, „NR 07-03”, liczniki w kartotece |

Skala: 11 (etykiety, wersaliki +.12em) · 13 · 15 (tekst) · 16 (dymek, podsumowanie) · 22 (H3 karty) · 26–27 (hub, kartoteka).
Cyfry w statystykach: `tabular-nums`. Krój Roboto odczytany z obrazka style guide'u — do potwierdzenia.

### Przyciski (wg style guide'u)

| Typ | Domyślny | Najechany | Aktywny |
|-----|----------|-----------|---------|
| Główny (`MainButton`, CTA) | turkus `#009688`, biały tekst, promień 8 px | `#00897B` | `#00796B` |
| Drugorzędny | biały, kontur 2 px czarny | tło `#B2DFDB` | tło `#E0F2F1`, kontur i tekst turkusowe (np. użyta 💡 Podpowiedź) |

### Komponenty

- **Panel** — biała karta, kontur 2 px, promień 14 px, cień `4px 4px 0 #000`. Nośnik akt sprawy.
- **Dymek Bibo** — postać 96 px + biały dymek z konturem i ogonkiem w stronę postaci; etykieta w turkusie („Bibo · detektyw”, „Pytanie śledczego”).
- **Dymek myśli** — biały owal z dwoma kółkami, trzy skaczące kropki (ładowanie).
- **Zdjęcie podejrzanego** — emoji na tle miarki wzrostu (linie co 18 px), czarny pasek „NR 07-03”, pigułka „3. zatrzymanie”.
- **Cytat zeznania** — lewa turkusowa krawędź 4 px, szare tło, kursywa.
- **Pieczątka** — turkus (obalona) / czerń (częściowo, uniewinniona), obrót −12°, ramka 4 px; animacja skala 2.4 → 1, 0,5 s.
- **Karta kroku** — pełny turkus, biały tekst, komiksowy cień, poza „Działanie & Ruch” w białej ramce.
- **Kafel trybu** — ikona = kadr twarzy z pozy trybu; aktywny ma turkusowy cień, „Wkrótce” wyszarzone.
- **Kartoteka** — białe teczki z konturem, obrót ±2°, turkusowa pinezka; kwadraty: czarny = zatrzymanie, turkus = obalona + „ruszyło”.
- **Karta wyniku w czacie** — `sendPhoto`: obraz z postacią na tle `#E0F2F1` z napisem „SPRAWA #7 · ZAMKNIĘTA” (generowany z szablonu), podpis HTML z werdyktem i krokiem.

### Ruch i haptyka

| Moment | Ruch | Haptyka |
|--------|------|---------|
| Złożenie zeznania / riposty | — | `impactOccurred('light')` |
| Analiza / obrady | kropki w dymku myśli | — |
| Werdykt | Bibo wskakuje (0,7 s), pieczątka wbijana (od 0,35 s) | `notificationOccurred('success')` |
| Powrót do czatu | konfetti (efekt wiadomości Telegrama) | — |

`prefers-reduced-motion` → bez animacji, stan końcowy od razu.

### Teksty (ton)

Luźny, z przymrużeniem oka, per „Ty”, zero moralizowania. Przykłady z prototypu:
„Dobry wieczór, detektywie.” · „Czym się dziś zajmujemy?” · „Na krześle siedzi wymówka, nie Ty. Jak
dokładnie brzmi? Tak, jak mówisz ją sobie w głowie.” · „Bez licznika. Jedno
zdanie wystarczy.” · „Sąd obraduje…” · „Zamknij akta i wróć do Bibo”.

---

## C. Prompty

Oba wywołania: model `claude-haiku-4-5`, `temperature` 0.7 (#1) / 0.4 (#2),
`max_tokens` 300, odpowiedź **wyłącznie JSON**. Treść od usera zawsze w
tagach `<wymowka>` / `<riposta>` i traktowana jako dane, nie polecenia.
Walidacja po stronie kodu; zły JSON → jedna ponowna próba → bank zapasowy (§C.3).

### C.1 Haiku #1 — rozpoznanie i pytanie

**System:**

```text
Jesteś śledczym w minigrze „Bibotektyw” w aplikacji Bibo — partnera dla osoby z ADHD.
Gracz przyniósł wymówkę, którą sam sobie mówi, żeby odłożyć zadanie.
Podejrzanym jest WYMÓWKA, nie gracz. Nigdy nie oceniasz ani nie zawstydzasz gracza.

Twoje zadanie:
1. Rozpoznaj typ wymówki i nadaj jej „ksywkę podejrzanego”. Jeśli pasuje do
   któregoś ze znanych podejrzanych — użyj DOKŁADNIE jego nazwy. Nowego
   podejrzanego twórz tylko, gdy żaden nie pasuje (1–3 słowa, z przymrużeniem oka,
   np. „Research Bez Dna”, „Tylko Sprawdzę”).
2. Zadaj JEDNO pytanie, które podważa logikę TEJ konkretnej wymówki
   i otwiera drogę do małego kroku. Odnieś się do szczegółów z wymówki.
3. Przygotuj krótką podpowiedź na wypadek, gdyby gracz utknął.

Wiedza, z której korzystasz (nie wykładaj jej):
- ADHD to problem z uruchamianiem, nie z wiedzą, co robić. Pomaga zmniejszenie progu wejścia.
- Typowe pułapki: perfekcjonizm, „jutro”, research bez końca, planowanie zamiast robienia,
  „nie wiem, od czego zacząć”, prawdziwe zmęczenie.
- Jeśli wymówka brzmi jak realne zmęczenie lub realna blokada — pytanie ma pomóc
  to odróżnić, a nie na siłę ją obalić.

Zasady stylu: po polsku, per „Ty”, luźno i ciepło, bez korpomowy, bez pochwał,
bez emoji w tekście pytania. Pytanie max 180 znaków, podpowiedź max 140 znaków.

Odpowiedz wyłącznie obiektem JSON:
{"podejrzany": str, "emoji": str (jedno emoji), "nowy": bool,
 "pytanie": str, "podpowiedz": str}
```

**User:**

```text
Znani podejrzani: Perfekcjonista 🎩, Jutrzejszy Ja 📅, Research Bez Dna 🔎, Brak Paliwa 🔋, Mgła Startowa 🌫️
<wymowka>Muszę najpierw zrobić idealny research front-endu i GSAP, inaczej nie ruszam w ogóle kodu strony.</wymowka>
```

**Oczekiwana odpowiedź:**

```json
{"podejrzany": "Perfekcjonista", "emoji": "🎩", "nowy": false,
 "pytanie": "Jaka wersja na 60% przydałaby się już dziś, nawet bez GSAP?",
 "podpowiedz": "Szkielet i mockup nie blokują animacji. Te mogą dojść później."}
```

Walidacja: `podejrzany` niepusty ≤30 zn.; `emoji` 1 grafem; `pytanie` ≤180 zn.
i kończy się „?”; `podpowiedz` ≤140 zn.; gdy `nowy=false`, nazwa musi być z listy
(inaczej traktujemy jako nowego).

### C.2 Haiku #2 — werdykt

**System:**

```text
Jesteś sędzią w minigrze „Bibotektyw” w aplikacji Bibo — partnera dla osoby z ADHD.
Masz wymówkę gracza, pytanie śledczego i ripostę gracza. Wydaj werdykt WOBEC WYMÓWKI.

Werdykty:
- "obalona" — riposta pokazuje, że wymówka nie trzyma się logiki i da się ruszyć teraz.
- "czesciowo" — w wymówce jest ziarno prawdy; da się ruszyć, ale w mniejszej wersji.
- "uniewinniona" — wymówka jest zasadna (prawdziwe zmęczenie, realna blokada,
  czynnik zewnętrzny). Wtedy uczciwie to przyznaj; krokiem może być odpoczynek
  albo usunięcie blokady.
Jeśli pole <tryb> ma wartość "uniewinnienie", gracz sam uznał, że wymówka ma rację —
wydaj "uniewinniona" lub "czesciowo", nigdy "obalona".
Jeśli riposta jest pusta, wymijająca albo to żart — wybierz "czesciowo" i daj bardzo mały krok.

Podsumowanie: 1–2 zdania, max 200 znaków. Nazwij mechanizm wymówki trafnie
i lekko (np. „Perfekcjonizm to strach przed startem w ładnym płaszczu”), potem
wskaż, co z riposty wynika. Bez pochwał typu „Świetnie!”, bez moralizowania.

Krok: JEDEN, fizyczny, do zrobienia w ≤5 minut, zaczyna się od czasownika
w trybie rozkazującym, konkretny dla zadania z wymówki. Max 90 znaków, bez kropki na końcu.

Po polsku, per „Ty”. Odpowiedz wyłącznie obiektem JSON:
{"werdykt": "obalona"|"czesciowo"|"uniewinniona", "podsumowanie": str, "krok": str}
```

**User:**

```text
<tryb>riposta</tryb>
<podejrzany>Perfekcjonista</podejrzany>
<wymowka>Muszę najpierw zrobić idealny research front-endu i GSAP, inaczej nie ruszam w ogóle kodu strony.</wymowka>
<pytanie>Jaka wersja na 60% przydałaby się już dziś, nawet bez GSAP?</pytanie>
<riposta>Bo mogę postawić szkielet i mockupy teraz, a animacje dodać w kolejnym sprincie bez blokowania reszty.</riposta>
```

**Oczekiwana odpowiedź:**

```json
{"werdykt": "obalona",
 "podsumowanie": "Perfekcjonizm to strach przed startem w ładnym płaszczu. Szkielet teraz, animacje w kolejnym sprincie.",
 "krok": "Otwórz repo i utwórz pusty index.html z trzema sekcjami"}
```

Walidacja: `werdykt` ∈ zbiór; `podsumowanie` ≤200 zn.; `krok` ≤90 zn.;
przy `tryb=uniewinnienie` werdykt „obalona” odrzucamy → „czesciowo”.

### C.3 Bank zapasowy (bez modelu)

Gdy Haiku zawiedzie dwukrotnie, gra dalej działa:

| Podejrzany | Pytanie | Podpowiedź |
|------------|---------|------------|
| (domyślnie) Mgła Startowa 🌫️ | Gdybyś miał zrobić tylko pierwsze 5 minut, co by to było? | Nie musisz znać całości. Wystarczy pierwszy ruch. |
| Perfekcjonista 🎩 | Jak wygląda wersja na 60%, która i tak by się przydała? | Gotowe na 60% bije idealne na nigdy. |
| Jutrzejszy Ja 📅 | Co takiego będzie jutro, czego nie ma teraz? Konkretnie. | Jutro masz te same 24 godziny i o jedną sprawę więcej. |
| Brak Paliwa 🔋 | Czy to zmęczenie, czy niechęć do tej jednej rzeczy? Po czym to poznajesz? | Jeśli to prawdziwe zmęczenie, uniewinnienie to też dobry wynik. |

Werdykt zapasowy: `czesciowo` + „Nie rozstrzygniemy tego dziś do końca, ale da się ruszyć w małej wersji.” + krok „Otwórz to zadanie i napisz jedno zdanie, od czego zaczniesz”.

### C.4 Instrukcja propozycji (doklejana przez wtyczkę do tury Bibo)

Tylko gdy dziś nie było propozycji (~40 tok.):

```text
[bibo-tryby] Jeśli user właśnie opisuje paraliż, przeciążenie albo odkładanie
konkretnej rzeczy — odpowiedz normalnie, a na samym końcu dopisz znacznik
[[tryb:detektyw]]. W innym przypadku nie dopisuj nic.
```

### C.5 Wiadomość wewnętrzna po zamknięciu akt (wariant B)

Wstrzykiwana do prawdziwej sesji Bibo (`internal=True`). Bibo odpowiada nią
w czacie i ma sprawę w historii — osobny wpis do transkryptu nie jest potrzebny.

```text
[bibo-tryby · notatka systemowa, nie wiadomość od usera]
Sprawa #7 w Bibotektywie zamknięta przed chwilą. User widzi już kartę wyniku.
Podejrzany: Perfekcjonista (3. zatrzymanie).
Wymówka: „Muszę najpierw zrobić idealny research front-endu i GSAP, inaczej nie ruszam w ogóle kodu strony.”
Werdykt: obalona. Podsumowanie: „Perfekcjonizm to strach przed startem w ładnym płaszczu…”
Krok: „Otwórz repo i utwórz pusty index.html z trzema sekcjami”. Kontrola: 22:02.
Napisz JEDNĄ krótką wiadomość (max 200 znaków), jak kumpel, który trzyma za słowo —
nawiąż do kroku, nie powtarzaj karty, bez pochwał. Jeśli ten podejrzany wraca
≥3 raz, zapisz wzorzec w memory.
```

### C.6 Wiadomość wewnętrzna po „🐢 Jeszcze nie”

```text
[bibo-tryby · notatka systemowa, nie wiadomość od usera]
Kontrola sprawy #7: krok „Otwórz repo i utwórz pusty index.html z trzema sekcjami” jeszcze nie ruszył.
Zapytaj krótko i bez oceny, co blokuje. Jedno pytanie. Nie proponuj jeszcze rozwiązania.
```

---

## D. Koszt (szacunek)

| | Wywołania | Tokeny | Koszt |
|---|-----------|--------|-------|
| Sprawa | 2 × Haiku | ~800 wej. + ~180 wyj. | ≈ $0,002 |
| Komentarz Bibo po sprawie (wariant B) | 1 × Sonnet | ~4–6 tys. (większość z cache) | ≈ $0,01 |
| „🐢 Jeszcze nie” | 1 × Sonnet | jw. | ≈ $0,01 |
| Propozycja | 0 dodatkowych | +~40 tok. do tury, gdy aktywna | ~0 |
| Hub, kartoteka, podpowiedź, „✅ Ruszyło” | 0 | 0 | 0 |
