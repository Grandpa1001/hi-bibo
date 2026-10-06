"""Eksport i usuwanie danych stanu dnia (prywatność): `/stan_eksport` i `/stan_usun`.

Dane stanu leżą tylko na tej instancji (`stan.sqlite3`). Eksport wysyła je do czatu właściciela jako plik JSON
(plik tymczasowy znika zaraz po wysyłce), usuwanie kasuje wszystko jedną transakcją i czyści plik bazy.
Usuwanie jest nieodwracalne, więc wymaga jawnego potwierdzenia w tej samej komendzie: `/stan_usun potwierdzam`.
Poza zakresem tej komendy zostają: karta sprawy (jej usuwa narzędzie `bibo_karta`), notatki, które Bibo zapisał
we własnej pamięci Hermesa (np. „POMYSŁ: …”), oraz wiadomości w historii Telegrama.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

from . import kontakt, magazyn, stan

log = logging.getLogger("bibo-tryby")

POTWIERDZENIE = "potwierdzam"


def opis_danych(w: str) -> str:
    n = stan.policz_dane(w)
    return (f"{n['wpisy_stanu']} wpisów stanu, {n['sygnaly_stanu']} sygnałów, {n['kronika']} wpisów Kroniki "
            f"i {n['aktywnosc']} dni aktywności")


def pytanie_o_usuniecie(w: str) -> str:
    return (f"To usunie na stałe wszystkie dane stanu dnia: {opis_danych(w)}. Nie da się tego cofnąć. "
            f"Nie usuwa karty sprawy, notatek w pamięci Bibo ani wiadomości w historii Telegrama. "
            f"Jeśli chcesz kopię, najpierw użyj /stan_eksport. Aby usunąć, wyślij: /stan_usun {POTWIERDZENIE}")


def usun(w: str, raw_args: str = "") -> str:
    """`/stan_usun` bez potwierdzenia tylko pyta; z potwierdzeniem kasuje i mówi dokładnie, co zniknęło."""
    if (raw_args or "").strip().lower() != POTWIERDZENIE:
        return pytanie_o_usuniecie(w)
    try:
        usuniete = stan.usun_wszystko(w)
    except Exception:
        log.warning("bibo-tryby: usuwanie danych stanu", exc_info=True)
        return "Nie udało się usunąć danych — nic nie zostało zmienione. Spróbuj jeszcze raz."
    tekst = (f"Usunięto dane stanu dnia: {usuniete['wpisy_stanu']} wpisów, {usuniete['sygnaly_stanu']} sygnałów, "
             f"{usuniete['kronika']} wpisów Kroniki i resztę zapisów pomocniczych. Zaczynamy od zera.")
    if not usuniete["plik_wyczyszczony"]:
        tekst += (" Uwaga: plik bazy był w tej chwili używany, więc jego fizyczne czyszczenie jeszcze trwa — "
                  "w razie potrzeby wyślij /stan_usun potwierdzam ponownie za minutę.")
    return tekst


def zapisz_plik(w: str, katalog: Path) -> Path:
    """Eksport do pliku `stan-RRRR-MM-DD.json` w podanym (prywatnym, tymczasowym) katalogu; uprawnienia tylko dla właściciela."""
    dane = stan.eksport(w)
    sciezka = katalog / f"stan-{kontakt.teraz().astimezone(kontakt.strefa()):%Y-%m-%d}.json"
    fd = os.open(sciezka, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dane, f, ensure_ascii=False, indent=2)
    return sciezka


async def wyslij_eksport(w: str, uslugi) -> bool:
    """Wysyła plik do czatu właściciela. Katalog tymczasowy z kopią znika zawsze, także po błędzie."""
    if not getattr(uslugi, "bot", None):
        return False
    try:
        with tempfile.TemporaryDirectory(dir=magazyn.katalog(), prefix=".eksport-") as katalog:
            os.chmod(katalog, 0o700)
            sciezka = zapisz_plik(w, Path(katalog))
            await uslugi.bot.wywolaj("sendDocument", {"chat_id": w, "caption": "Eksport danych stanu dnia (JSON). Dane zostają też na tej instancji."},
                                     pliki={"document": str(sciezka)})
        return True
    except Exception as e:
        log.warning("bibo-tryby: eksport danych stanu: %s", type(e).__name__)
        try:
            await uslugi.bot.wywolaj("sendMessage", {"chat_id": w, "text": "Nie udało się wysłać eksportu. Spróbuj jeszcze raz za chwilę."})
        except Exception:
            pass
        return False
