# Karta sprawy i check-in (Bibo)

Bibo trzyma **jedną bieżącą sprawę** (cel, przeszkoda, krok, miejsce zatrzymania) i może umówić **jeden check-in**,
czyli jednorazowy powrót o wybranej porze. Wszystko zapisuje się tylko po Twojej zgodzie i da się to zmienić lub odwołać.

## Jak używać (w rozmowie)

- „Co mamy zapisane?” · „zmień krok” · „odłóż” · „skończone” · „usuń tę sprawę”.
- „Wróć do tego o 15:30” / „za godzinę” → Bibo odpowiada „Zaplanowane na dziś, 15:30. Możesz anulować” dopiero po zapisie.
- „Anuluj check-in” — działa do chwili wysyłki. Gdy wiadomość już wyszła, Bibo powie to wprost.
- „Daj mi spokój na 3 godziny” → pauza. Check-in z czasu pauzy jest pomijany i po jej końcu nie wychodzi.
- W godzinach ciszy (domyślnie 22–8) Bibo się nie odzywa. Godziny zmienisz w `local/bibo_pulse.json` (`quiet_from`, `quiet_to`).
- Odpowiedź na check-in: przyciski „Ruszyłem / Utknąłem / Odkładam” albo zwykły tekst. Brak odpowiedzi nie wywołuje kolejnej wiadomości.

## Wymagania

- Jeden właściciel: dokładnie jedno id w `TELEGRAM_ALLOWED_USERS` (bez `*`).
- Narzędzie włączone: `hermes config set platform_toolsets.telegram "[memory,bibo_karta]"` (robi to też `install.sh`).

## Wyłączanie

- Same check-iny: w `local/bibo_tryby/ustawienia.json` ustaw `{"checkiny": false}`. Najbliższy przebieg pętli (do 60 s)
  anuluje całą kolejkę; nic nie zostaje do wysłania.
- Całą kartę: usuń `bibo_karta` z `platform_toolsets.telegram`.

## Dane i powrót do poprzedniej wersji

- Dane: `local/bibo_tryby/karta.sqlite3`. Tabela `checkiny` jest dodawana bez zmiany istniejących; przed jej dodaniem
  powstaje kopia `karta.sqlite3.przed-checkinami`.
- Powrót do wersji sprzed check-inów: `hermes bibo update` ze starej wersji, a w razie potrzeby podmień bazę na kopię.
  Nie ma drugiego harmonogramu: wysyła wyłącznie pętla `kontrola.py`, którą stara wersja też uruchamia.
- Terminy starsze niż 15 min w chwili przejęcia (np. po restarcie) wygasają bez wysyłki.
