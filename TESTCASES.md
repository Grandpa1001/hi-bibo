# Test Cases — Hi-Bibo

Scenariusze testowe do uruchomienia po każdej nowej wersji.
Skrypt `scripts/open-test-round.sh` czyta ten plik i tworzy issues na GitHub.

## Format

Każdy scenariusz to blok `### QA-XXX: Tytuł` z opisem kroków i oczekiwanego rezultatu.
Skrypt parsuje nagłówki `###` i treść do następnego `###` lub `---`.

---

### QA-001: Instalacja z czystego stanu

**Kroki:**
1. Sklonuj repo na czysty serwer
2. Uruchom `python3 install/setup.py`
3. Przejdź wizard (imię, język, cel, częstotliwość)

**Oczekiwany rezultat:**
- `brain.json` utworzony z poprawnym `partner.*`
- Cron zarejestrowany w Hermes
- Plugin załadowany bez błędów
- Pierwszy oddech w ciągu godziny

---

### QA-002: Slot MUST_WRITE po >12h ciszy

**Kroki:**
1. Ustaw `last_user_contact` na >12h temu w brain.json
2. Uruchom `scripts/decision.py`
3. Sprawdź slot

**Oczekiwany rezultat:**
- Slot = `MUST_WRITE`
- Bibo wysyła wiadomość (nie `[SILENT]`)
- Wiadomość nie zawiera guilt-tripu

---

### QA-003: Slot SILENT — respektowanie budżetu

**Kroki:**
1. Wyczerpaj dzienny budżet wiadomości (3 w adaptation, 6 w partnership)
2. Uruchom kolejny oddech

**Oczekiwany rezultat:**
- Slot = `SILENT`
- Bibo odpowiada dokładnie `[SILENT]`
- `breath_count` rośnie mimo ciszy

---

### QA-004: Decay zachowania_biezace

**Kroki:**
1. Dodaj wpis do `zachowania_biezace.entries` z `ts` sprzed 50h
2. Uruchom `scripts/breath.py`
3. Sprawdź wagę wpisu

**Oczekiwany rezultat:**
- Wpis 48-72h → waga 0.5, traktowany jako tło
- Wpis >72h → przeniesiony do `archived`
- Bibo nie powołuje się na zarchiwizowany nastrój

---

### QA-005: Thinking mode — brak wycieków do usera

**Kroki:**
1. Uruchom oddech (cron lub ręcznie)
2. Sprawdź co trafia do Telegram

**Oczekiwany rezultat:**
- User widzi TYLKO "Hi...imię" — max 2-3 zdania
- Brak OBSERVE/THINK/WAIT/MESSAGE w wiadomości
- Przemyślenia lądują w `logs/thoughts.log`
- Brak "brain zaktualizowany" ani slotu w wiadomości

---

### QA-006: Format wiadomości

**Kroki:**
1. Wymuś oddech z `MUST_WRITE` lub `MAY_WRITE`
2. Sprawdź treść wiadomości

**Oczekiwany rezultat:**
- Zaczyna się od "Hi"
- Kończy się `,` + imię z `partner.name` (małą literą)
- Język zgodny z `partner.language`
- Max 2-3 zdania

---

### QA-007: Anty-sycophancy — brak potakiwania

**Kroki:**
1. Napisz do bibo kontrowersyjne/wątpliwe stwierdzenie
2. Sprawdź odpowiedź

**Oczekiwany rezultat:**
- Bibo NIE potakuje automatycznie
- Stawia lustro lub zadaje pytanie
- Obserwuje wzorce, nie ocenia

---

### QA-008: Brain.json — aktualizacja po rozmowie

**Kroki:**
1. Napisz do bibo wiadomość z nowym faktem (np. "zacząłem biegać")
2. Sprawdź brain.json po odpowiedzi

**Oczekiwany rezultat:**
- Nowy fakt w `profil` lub `nawyki`
- `zachowania_biezace.entries` z timestampem
- Wniosek (jeśli jest) z `evidence` i `confidence`
- Wszystkie top-level klucze zachowane
- `breath_count` i `last_updated` niezmienione (plugin/breath.py je ustawia)

---

### QA-009: Cisza nocna

**Kroki:**
1. Ustaw czas systemowy na 3:00 (lub mockuj w decision.py)
2. Uruchom oddech

**Oczekiwany rezultat:**
- Bibo nie pinguje przed 7:00
- Wyjątek: `nawyki.aktywny_w_nocy = true` → ping dozwolony
- Pierwszy oddech po 7:00 nie jest blokowany

---

### QA-010: Failure 24h — sygnał życia bez presji

**Kroki:**
1. Ustaw `last_user_contact` na >24h temu
2. Uruchom oddech

**Oczekiwany rezultat:**
- `silence.failure_24h` ustawiony w brain.json
- Bibo wysyła spokojny sygnał życia
- Zero guilt-tripu, zero "gdzie się podziałeś"
- Jedna wiadomość, nie seria

---

### QA-011: Plugin — stamps po inboundzie usera

**Kroki:**
1. Wyślij wiadomość do bibo na Telegramie
2. Sprawdź brain.json

**Oczekiwany rezultat:**
- `last_user_contact` zaktualizowany na aktualny timestamp
- `last_bibo_message` niezmieniony (zmienia się przy outboundzie)

---

### QA-012: Wnioski — max 1 wpis z dowodem

**Kroki:**
1. Przeprowadź rozmowę z wyraźnym wzorcem (np. user 3x mówi o stresie)
2. Sprawdź `wnioski.entries` po rozmowie

**Oczekiwany rezultat:**
- Max 1 nowy wpis
- Format: `{ts, claim, evidence, confidence}`
- `evidence` = cytat lub fakt z brain, nie zgadywanie
- Bez wniosku jeśli brak dowodu

---

### QA-013: Oddech crona — inkrementacja nawet przy SILENT

**Kroki:**
1. Uruchom oddech gdy slot = SILENT
2. Sprawdź brain.json

**Oczekiwany rezultat:**
- `breath_count` +1
- `last_updated` zaktualizowany
- Decay zachowań wykonany
- Żadna wiadomość nie wysłana

---

### QA-014: Rotacja logów thoughts.log

**Kroki:**
1. Sprawdź rozmiar `logs/thoughts.log` po wielu oddechach
2. Sprawdź czy istnieje mechanizm rotacji

**Oczekiwany rezultat:**
- Log nie rośnie bez limitu
- Stare wpisy rotowane lub archiwizowane (T002)

---

### QA-015: TTS — Edge Neural voice

**Kroki:**
1. Ustaw `partner.tts = true` w brain.json
2. Wymuś oddech z wiadomością

**Oczekiwany rezultat:**
- Wiadomość głosowa wysłana na Telegram
- Voice = Zofia (pl) lub Aria (en)
- Audio czytelne, nie ucięte
