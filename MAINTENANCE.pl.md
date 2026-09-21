[🇬🇧 English](MAINTENANCE.md) | 🇵🇱 Polski

# Bibo — Poradnik operacyjny

To jest bieżąca checklista utrzymania **działającej** instalacji Bibo, po
tym jak skończysz setup (patrz [README.pl.md](README.pl.md)). To porady
z rekomendowanym cyklem, nie jednorazowe zadanie budowlane — w
przeciwieństwie do [Analiza.MD](Analiza.MD), która dokumentuje *dlaczego*
Bibo jest zbudowane tak jak jest.

---

## Co tydzień

**`hermes doctor`** — łapie odchylenia instalacji zanim staną się realnym problemem.

**`/usage`** — sprawdź rzeczywiste zużycie tokenów względem celów poniżej.
Jeśli konsekwentnie przekraczasz — patrz "Tuning kosztów" niżej.

## Co miesiąc

### 1. Sprawdzenie kosztu i rozmiaru promptu
```bash
hermes prompt-size --profile bibo
```
- **Cel:** stały narzut promptu (SOUL.md + AGENTS.md) poniżej 1500 tokenów
- **Cel:** koszt miesięczny poniżej $5 (porównaj z historią `/usage`)
- Jeśli któryś cel przekroczony: sprawdź czy `prompt_cache: true` w
  `config.yaml` jest faktycznie honorowany przez Twoją wersję Hermesa,
  i czy `skills.auto_load` wciąż jest pusty (powinien być — skill
  krytycznego myślenia ładuje się na żądanie, nie zawsze).

### 2. Audyt bezpieczeństwa
```bash
hermes security audit
```
To skan łańcucha zależności, nie pełna certyfikacja bezpieczeństwa —
przeczytaj ostrzeżenie z tutoriala zanim uznasz że to znaczy "bezpieczne".
Połącz to z ręcznym sprawdzeniem:
- Czy `TELEGRAM_BOT_TOKEN` / `ANTHROPIC_API_KEY` wciąż siedzi w plaintext
  `.env`, czy przeniesiony do `hermes secrets`? Przenieś jeśli nie.
- Jakiś plugin, skill albo serwer MCP zainstalowany, którego nie potrafisz
  wytłumaczyć czemu tam jest? Usuń go.

### 3. Self-audit (agent audytuje sam siebie)
Uruchom dokładnie ten prompt na Bibo (z tutoriala Hermesa — zostaw jak jest,
nie parafrazuj, jest zaprojektowany żeby wymusić audyt bez zmian bez zgody):

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

Zapisz wynik do `logs/audit-YYYY-MM.md`. Przejrzyj rekomendacje, zastosuj
tylko to z czym się faktycznie zgadzasz — ręcznie, nie pozwalając agentowi
auto-aplikować.

## Co kwartał

### Restore drill
Backup którego nigdy nie przywróciłeś to zgadywanka, nie plan.
```bash
hermes backup
# na jednorazowej VM albo kontenerze:
hermes import <plik backupu>
hermes doctor
```
Jeśli to nie zadziała, Twój realny plan backupu właśnie zawiódł — napraw
to teraz, nie podczas prawdziwej awarii.

### Rotacja tokenu
Zrotuj `TELEGRAM_BOT_TOKEN` przez @BotFather. Zaktualizuj `hermes secrets`
(albo `.env` jeśli jeszcze nie migrowałeś — patrz miesięczny check
bezpieczeństwa wyżej).

## W razie potrzeby

### Tuning kosztów
Jeśli koszt miesięczny konsekwentnie przekracza $5 mimo prompt cachingu:
1. Sprawdź breakdown `/usage` — to głównie tokeny input (kontekst) czy output?
2. Jeśli dużo inputu: historia sesji (5-10 wymian wg decyzji #15 z Etapu 3)
   może być za hojna dla Twojego wzorca użycia — rozważ przycięcie.
3. Jeśli wciąż wysoko: fallback `claude-haiku-4-5-20251001` w `config.yaml`
   jest tylko na awarie, nie na rutynowy routing (zgodnie z non-goals
   w Analiza.MD — "Auxiliary model routing" był świadomie odrzucony).
   Wróć do tej decyzji tylko jeśli koszt stanie się dominującym ograniczeniem.

### Konfiguracja celu backupu (jednorazowo, zrób zanim będzie potrzebne)
Skonfiguruj `hermes backup` żeby wypychał do Backblaze B2 albo S3 —
**nie** do folderu na tym samym VPS. Backup który umiera razem z maszyną
którą chroni nie jest backupem.

---

## Czemu ten plik istnieje osobno od Analiza.MD

Analiza.MD to rejestr decyzji architektonicznych — wyjaśnia *dlaczego* Bibo
nie ma crona, pluginu, minimalną pamięć. Milestones M6 (optymalizacja), M7
(recovery/security), M8 (self-audit) w tamtym dokumencie były pierwotnie
zadaniami budowlanymi jednorazowymi, ale w rzeczywistości są cyklicznymi
praktykami operacyjnymi. Ten plik jest ich nowym domem, jako żywy dokument
do którego faktycznie wracasz według harmonogramu — Analiza.MD zostaje
historycznym zapisem decyzji rebuildu.
