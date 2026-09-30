"""Jedna bieżąca sprawa usera: cel, przeszkoda, krok, miejsce zatrzymania.

Małe SQLite w `$HERMES_HOME/local/bibo_tryby/karta.sqlite3` (przeżywa aktualizacje).
Nie dotyka pamięci Hermesa ani kartoteki Bibotektywa. Na właściciela przypada
najwyżej jedna karta `aktywna`; zmiany są krótkimi transakcjami z kontrolą wersji
rekordu, więc spóźniony zapis nie nadpisze nowszej decyzji ani nie przywróci
usuniętej karty. W tym samym pliku leży tabela `checkiny` (jeden oczekujący na kartę;
obsługuje ją `checkin.py`). Zakończenie, odłożenie i usunięcie karty anuluje jej
oczekujący check-in w tej samej transakcji.
"""
from __future__ import annotations

import os
import re
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path

from . import magazyn

STATUSY = ("aktywna", "odlozona", "zakonczona")
POLA = ("cel", "przeszkoda", "krok", "zatrzymanie")
MAKS_POLE = 300

_SCHEMAT = """
CREATE TABLE IF NOT EXISTS karty (
    id TEXT PRIMARY KEY,
    wlasciciel TEXT NOT NULL,
    cel TEXT NOT NULL DEFAULT '',
    przeszkoda TEXT NOT NULL DEFAULT '',
    krok TEXT NOT NULL DEFAULT '',
    zatrzymanie TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('aktywna', 'odlozona', 'zakonczona')),
    zaktualizowano TEXT NOT NULL,
    wersja INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS jedna_aktywna ON karty (wlasciciel) WHERE status = 'aktywna';
CREATE TABLE IF NOT EXISTS checkiny (
    id TEXT PRIMARY KEY,
    karta_id TEXT NOT NULL,
    wlasciciel TEXT NOT NULL,
    kanal TEXT NOT NULL DEFAULT 'telegram',
    termin_utc TEXT NOT NULL,
    strefa TEXT NOT NULL,
    status TEXT NOT NULL,
    proby INTEGER NOT NULL DEFAULT 0,
    id_wiadomosci TEXT,
    utworzono TEXT NOT NULL,
    zaktualizowano TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS jeden_oczekujacy ON checkiny (karta_id) WHERE status IN ('oczekuje', 'wysylanie');
"""


class BladKarty(Exception):
    """`kod`: brak_wlasciciela | brak_karty | jest_aktywna | konflikt | dane."""

    def __init__(self, kod: str, komunikat: str):
        super().__init__(komunikat)
        self.kod = kod
        self.komunikat = komunikat


def wlasciciel() -> str | None:
    """Jedyny dozwolony user Telegrama. Bez jednoznacznego właściciela funkcja jest wyłączona."""
    ids = {x.strip() for x in os.environ.get("TELEGRAM_ALLOWED_USERS", "").replace(";", ",").split(",") if x.strip()}
    return next(iter(ids)) if len(ids) == 1 and "*" not in ids else None


def _polacz(sciezka: Path | None = None) -> sqlite3.Connection:
    p = sciezka or magazyn.katalog() / "karta.sqlite3"
    db = sqlite3.connect(p, timeout=5, isolation_level=None)   # transakcje jawnie (BEGIN IMMEDIATE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    _kopia_przed_zmiana_schematu(db, p)
    db.executescript(_SCHEMAT)
    return db


def _kopia_przed_zmiana_schematu(db: sqlite3.Connection, p: Path) -> None:
    """Gdy istnieje baza sprzed check-inów, jednorazowo zapisuje jej kopię obok (powrót do poprzedniej wersji)."""
    tabele = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "karty" in tabele and "checkiny" not in tabele:
        kopia = p.with_name(p.name + ".przed-checkinami")
        if not kopia.exists():
            dst = sqlite3.connect(kopia)
            try:
                db.backup(dst)
            finally:
                dst.close()


def _wiersz(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r else None


def _czysc(pola: dict) -> dict:
    """Tylko znane pola; tekst usera bez znaków < > i nadmiaru białych znaków."""
    wynik = {}
    for k, v in pola.items():
        if k not in POLA or v is None:
            continue
        if not isinstance(v, str):
            raise BladKarty("dane", f"Pole „{k}” musi być tekstem.")
        t = re.sub(r"\s+", " ", v.replace("<", "‹").replace(">", "›")).strip()
        if len(t) > MAKS_POLE:
            raise BladKarty("dane", f"Pole „{k}” ma {len(t)} znaków, limit {MAKS_POLE}.")
        wynik[k] = t
    return wynik


def _wymagaj_wlasciciela(w: str | None) -> str:
    if not w:
        raise BladKarty("brak_wlasciciela", "Karta sprawy jest niedostępna (brak jednego właściciela profilu).")
    return str(w)


def _teraz() -> str:
    return magazyn.iso()


def odczytaj(w: str, *, status: str | None = None, sciezka: Path | None = None) -> list[dict]:
    """Karty właściciela (najnowsze pierwsze); bez `status` wszystkie oprócz zakończonych."""
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        if status:
            rs = db.execute("SELECT * FROM karty WHERE wlasciciel=? AND status=? ORDER BY zaktualizowano DESC", (w, status))
        else:
            rs = db.execute("SELECT * FROM karty WHERE wlasciciel=? AND status!='zakonczona' "
                            "ORDER BY status='aktywna' DESC, zaktualizowano DESC", (w,))
        return [dict(r) for r in rs]


def aktywna(w: str, sciezka: Path | None = None) -> dict | None:
    kart = odczytaj(w, status="aktywna", sciezka=sciezka)
    return kart[0] if kart else None


def _anuluj_checkiny(db: sqlite3.Connection, w: str, kid: str, status: str = "anulowany") -> None:
    db.execute("UPDATE checkiny SET status=?, zaktualizowano=? WHERE karta_id=? AND wlasciciel=? AND status='oczekuje'",
               (status, _teraz(), kid, w))


def _zmien_status(db: sqlite3.Connection, w: str, kid: str, status: str, wersja: int | None) -> None:
    ograniczenie, arg = ("", ()) if wersja is None else (" AND wersja=?", (wersja,))
    n = db.execute("UPDATE karty SET status=?, zaktualizowano=?, wersja=wersja+1 WHERE id=? AND wlasciciel=?" + ograniczenie,
                   (status, _teraz(), kid, w, *arg)).rowcount
    if n == 0:
        raise BladKarty("konflikt", "Karta zmieniła się albo została usunięta — nic nie zapisano.")


def utworz(w: str, pola: dict, *, poprzednia: str | None = None, sciezka: Path | None = None) -> dict:
    """Nowa aktywna karta. Gdy jest już aktywna, trzeba zdecydować o niej: `poprzednia` = odloz|zakoncz|usun."""
    w = _wymagaj_wlasciciela(w)
    pola = _czysc(pola)
    if poprzednia not in (None, "odloz", "zakoncz", "usun"):
        raise BladKarty("dane", "„poprzednia” to: odloz, zakoncz albo usun.")
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            stara = db.execute("SELECT * FROM karty WHERE wlasciciel=? AND status='aktywna'", (w,)).fetchone()
            if stara:
                if not poprzednia:
                    raise BladKarty("jest_aktywna", "Jest już aktywna sprawa. Zapytaj usera, co z nią zrobić: "
                                    "odłożyć, zakończyć czy usunąć — i dopiero wtedy załóż nową.")
                _anuluj_checkiny(db, w, stara["id"])
                if poprzednia == "usun":
                    db.execute("DELETE FROM checkiny WHERE karta_id=? AND wlasciciel=?", (stara["id"], w))
                    db.execute("DELETE FROM karty WHERE id=? AND wlasciciel=?", (stara["id"], w))
                else:
                    _zmien_status(db, w, stara["id"], "odlozona" if poprzednia == "odloz" else "zakonczona", None)
            kid = "k_" + secrets.token_hex(4)
            db.execute("INSERT INTO karty (id, wlasciciel, cel, przeszkoda, krok, zatrzymanie, status, zaktualizowano) "
                       "VALUES (?,?,?,?,?,?, 'aktywna', ?)",
                       (kid, w, *(pola.get(k, "") for k in POLA), _teraz()))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        return dict(db.execute("SELECT * FROM karty WHERE id=?", (kid,)).fetchone())


def aktualizuj(w: str, pola: dict, *, wersja: int | None = None, sciezka: Path | None = None) -> dict:
    """Zmiana pól aktywnej karty. Podana `wersja` musi być aktualna (inaczej `konflikt`)."""
    w = _wymagaj_wlasciciela(w)
    pola = _czysc(pola)
    if not pola:
        raise BladKarty("dane", "Brak pól do zapisania.")
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            stara = db.execute("SELECT * FROM karty WHERE wlasciciel=? AND status='aktywna'", (w,)).fetchone()
            if not stara:
                raise BladKarty("brak_karty", "Nie ma aktywnej sprawy.")
            if wersja is not None and stara["wersja"] != wersja:
                raise BladKarty("konflikt", "Karta zmieniła się w międzyczasie — nic nie zapisano.")
            ust = ", ".join(f"{k}=?" for k in pola)
            db.execute(f"UPDATE karty SET {ust}, zaktualizowano=?, wersja=wersja+1 WHERE id=? AND wlasciciel=?",
                       (*pola.values(), _teraz(), stara["id"], w))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        return dict(db.execute("SELECT * FROM karty WHERE id=?", (stara["id"],)).fetchone())


def przenies(w: str, docelowy: str, *, wersja: int | None = None, sciezka: Path | None = None) -> dict:
    """`odlozona` / `zakonczona` dla aktywnej karty; `aktywna` wznawia najnowszą odłożoną
    (tylko gdy nie ma aktywnej)."""
    w = _wymagaj_wlasciciela(w)
    if docelowy not in STATUSY:
        raise BladKarty("dane", "Zły status.")
    zrodlowy = "odlozona" if docelowy == "aktywna" else "aktywna"
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            if docelowy == "aktywna" and db.execute(
                    "SELECT 1 FROM karty WHERE wlasciciel=? AND status='aktywna'", (w,)).fetchone():
                raise BladKarty("jest_aktywna", "Jest już aktywna sprawa — najpierw ją odłóż lub zakończ.")
            k = db.execute("SELECT * FROM karty WHERE wlasciciel=? AND status=? ORDER BY zaktualizowano DESC LIMIT 1",
                           (w, zrodlowy)).fetchone()
            if not k:
                raise BladKarty("brak_karty", "Nie ma takiej sprawy.")
            _zmien_status(db, w, k["id"], docelowy, wersja)
            if docelowy != "aktywna":
                _anuluj_checkiny(db, w, k["id"])   # odłożenie/zakończenie kasuje termin (nowy trzeba wybrać jawnie)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        return dict(db.execute("SELECT * FROM karty WHERE id=?", (k["id"],)).fetchone())


def usun(w: str, *, tylko_aktywna: bool = True, sciezka: Path | None = None) -> int:
    """Usuwa kartę na stałe (aktywną; z `tylko_aktywna=False` także odłożone). Zwraca liczbę usuniętych."""
    w = _wymagaj_wlasciciela(w)
    warunek = " AND status='aktywna'" if tylko_aktywna else ""
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM checkiny WHERE wlasciciel=? AND karta_id IN "
                   f"(SELECT id FROM karty WHERE wlasciciel=?{warunek})", (w, w))
        n = db.execute("DELETE FROM karty WHERE wlasciciel=?" + warunek, (w,)).rowcount
        db.execute("COMMIT")
    if n == 0:
        raise BladKarty("brak_karty", "Nie ma sprawy do usunięcia.")
    return n
