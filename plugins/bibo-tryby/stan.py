"""Stan dnia usera: wpisy samopoczucia (siatka energia × przyjemność, uwaga) i sygnały gorszego dnia.

Osobne małe SQLite w `$HERMES_HOME/local/bibo_tryby/stan.sqlite3` (przeżywa aktualizacje).
Nie dotyka `karta.sqlite3`, więc stara wersja wtyczki ignoruje ten plik, a ścieżka karty
i check-inów nie płaci za nic nowego. Ten moduł to sama warstwa danych: żadnego hooka,
narzędzia ani pracy w tle, więc nie dokłada nic do tury modelu ani do pętli kontroli.

Nazwa „check-in” w tym repo oznacza już uzgodniony powrót do sprawy (`checkin.py`),
dlatego wpis samopoczucia to tu „wpis stanu” (`wpisy_stanu`), a spec `wellbeing_signal`
to `sygnaly_stanu`.

Zasady:
- tryb dnia nie jest zapisywany osobno: to `cwiartka` ostatniego wpisu z dzisiejszego dnia usera;
- ćwiartkę liczy kod z osi, nie model; na osi zero wpada w spokojniejszą stronę
  (energia 0 = niska, przyjemność 0 = przyjemnie), środek siatki daje „stabilnie”;
- zmiana uwagi w ciągu dnia to nowy wpis z tymi samymi osiami, żeby zostawał ślad pory (FR-16);
- odpowiedź „nie” na pytanie z sygnału zapisuje tylko `potwierdzone=0` przy sygnale, nigdy wpis stanu;
- dane tylko lokalnie; właściciel jak w karcie (jedyne id w TELEGRAM_ALLOWED_USERS).
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import kontakt, magazyn

CWIARTKI = ("peak", "steady", "tension", "recovery")
UWAGA = ("hypofocus", "normal", "hyperfocus")
ZRODLA = ("manual", "widget", "inferred_confirmed")
RODZAJE = ("phrase", "late_hour", "short_messages", "long_session", "topic_switching", "abandoned_tasks")
CELE = ("bad_day", "hyperfocus", "hypofocus")
MAKS_NOTATKA = 300
OS = (-2, 2)

# FR-2: 3–4 słowa na ćwiartkę, do pominięcia. Tylko z tej listy, żeby dane zostały czyste.
SLOWA = {
    "peak": ("pełen energii", "skupiony", "zadowolony", "zmotywowany"),
    "steady": ("spokojny", "odprężony", "wdzięczny", "zrównoważony"),
    "tension": ("zestresowany", "podenerwowany", "rozdrażniony", "niespokojny"),
    "recovery": ("zmęczony", "przygaszony", "wyczerpany", "smutny"),
}

_SCHEMAT = """
CREATE TABLE IF NOT EXISTS wpisy_stanu (
    id TEXT PRIMARY KEY,
    wlasciciel TEXT NOT NULL,
    utworzono TEXT NOT NULL,
    energia INTEGER NOT NULL CHECK (energia BETWEEN -2 AND 2),
    przyjemnosc INTEGER NOT NULL CHECK (przyjemnosc BETWEEN -2 AND 2),
    cwiartka TEXT NOT NULL CHECK (cwiartka IN ('peak', 'steady', 'tension', 'recovery')),
    uwaga TEXT NOT NULL DEFAULT 'normal' CHECK (uwaga IN ('hypofocus', 'normal', 'hyperfocus')),
    slowo TEXT,
    notatka TEXT,
    zrodlo TEXT NOT NULL CHECK (zrodlo IN ('manual', 'widget', 'inferred_confirmed'))
);
CREATE INDEX IF NOT EXISTS wpisy_stanu_czas ON wpisy_stanu (wlasciciel, utworzono);
CREATE TABLE IF NOT EXISTS sygnaly_stanu (
    id TEXT PRIMARY KEY,
    wlasciciel TEXT NOT NULL,
    utworzono TEXT NOT NULL,
    rodzaj TEXT NOT NULL CHECK (rodzaj IN ('phrase', 'late_hour', 'short_messages', 'long_session', 'topic_switching', 'abandoned_tasks')),
    cel TEXT NOT NULL CHECK (cel IN ('bad_day', 'hyperfocus', 'hypofocus')),
    zapytano INTEGER NOT NULL DEFAULT 0,
    potwierdzone INTEGER
);
CREATE INDEX IF NOT EXISTS sygnaly_stanu_czas ON sygnaly_stanu (wlasciciel, utworzono);
CREATE TABLE IF NOT EXISTS siatka_pokazana (
    wlasciciel TEXT NOT NULL,
    dzien TEXT NOT NULL,
    PRIMARY KEY (wlasciciel, dzien)
);
"""
_gotowe: set[str] = set()   # bazy ze świeżo sprawdzonym schematem: nie powtarzamy go przy każdej turze
DNI_POKAZU = 14


class BladStanu(Exception):
    """`kod`: brak_wlasciciela | brak_wpisu | dane."""

    def __init__(self, kod: str, komunikat: str):
        super().__init__(komunikat)
        self.kod = kod
        self.komunikat = komunikat


def _wymagaj_wlasciciela(w: str | None) -> str:
    if not w:
        raise BladStanu("brak_wlasciciela", "Stan dnia jest niedostępny (brak jednego właściciela profilu).")
    return str(w)


def _polacz(sciezka: Path | None = None) -> sqlite3.Connection:
    p = sciezka or magazyn.katalog() / "stan.sqlite3"
    db = sqlite3.connect(p, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    if str(p) not in _gotowe:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(_SCHEMAT)
        _gotowe.add(str(p))
    return db


def _utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def cwiartka(energia: int, przyjemnosc: int) -> str:
    wysoka, przyjemnie = energia > 0, przyjemnosc >= 0
    if wysoka:
        return "peak" if przyjemnie else "tension"
    return "steady" if przyjemnie else "recovery"


def _os(nazwa: str, v) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not OS[0] <= v <= OS[1]:
        raise BladStanu("dane", f"„{nazwa}” to liczba całkowita od {OS[0]} do {OS[1]}.")
    return v


def _wybor(nazwa: str, v: str, dozwolone: tuple) -> str:
    if v not in dozwolone:
        raise BladStanu("dane", f"„{nazwa}” to jedno z: {', '.join(dozwolone)}.")
    return v


def _notatka(v) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        raise BladStanu("dane", "Notatka musi być tekstem.")
    t = re.sub(r"\s+", " ", v.replace("<", "‹").replace(">", "›")).strip()
    if len(t) > MAKS_NOTATKA:
        raise BladStanu("dane", f"Notatka ma {len(t)} znaków, limit {MAKS_NOTATKA}.")
    return t or None


def _dzien_utc(teraz: datetime, przesuniecie_dni: int = 0) -> tuple[str, str]:
    """Zakres [początek, koniec) lokalnej doby usera jako UTC; ISO o stałym formacie sortuje się tekstowo."""
    z = kontakt.strefa()
    d = teraz.astimezone(z).date() + timedelta(days=przesuniecie_dni)
    od = datetime(d.year, d.month, d.day, tzinfo=z)
    return _utc(od), _utc(od + timedelta(days=1))


# --- wpisy stanu ----------------------------------------------------------------

def zapisz_wpis(w: str, energia: int, przyjemnosc: int, *, uwaga: str = "normal", zrodlo: str = "manual",
                teraz: datetime | None = None, sciezka: Path | None = None) -> dict:
    """Jeden tap na siatce (FR-1). Brak wyboru uwagi = normal (FR-11)."""
    w = _wymagaj_wlasciciela(w)
    e, p = _os("energia", energia), _os("przyjemnosc", przyjemnosc)
    _wybor("uwaga", uwaga, UWAGA)
    _wybor("zrodlo", zrodlo, ZRODLA)
    wid = "w_" + secrets.token_hex(6)
    with closing(_polacz(sciezka)) as db:
        db.execute("INSERT INTO wpisy_stanu (id, wlasciciel, utworzono, energia, przyjemnosc, cwiartka, uwaga, zrodlo) "
                   "VALUES (?,?,?,?,?,?,?,?)",
                   (wid, w, _utc(teraz or kontakt.teraz()), e, p, cwiartka(e, p), uwaga, zrodlo))
        return dict(db.execute("SELECT * FROM wpisy_stanu WHERE id=?", (wid,)).fetchone())


def doprecyzuj(w: str, *, slowo: str | None = None, notatka: str | None = None,
               teraz: datetime | None = None, sciezka: Path | None = None) -> dict:
    """FR-2: słowo z ćwiartki i notatka dopisane do ostatniego wpisu z dziś. Oba opcjonalne."""
    w = _wymagaj_wlasciciela(w)
    nota = _notatka(notatka)
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            r = _ostatni_dzis(db, w, teraz or kontakt.teraz())
            if not r:
                raise BladStanu("brak_wpisu", "Dziś nie ma wpisu stanu do doprecyzowania.")
            if slowo is not None and slowo not in SLOWA[r["cwiartka"]]:
                raise BladStanu("dane", f"Słowo musi być jednym z: {', '.join(SLOWA[r['cwiartka']])}.")
            db.execute("UPDATE wpisy_stanu SET slowo=COALESCE(?, slowo), notatka=COALESCE(?, notatka) WHERE id=?",
                       (slowo, nota, r["id"]))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        return dict(db.execute("SELECT * FROM wpisy_stanu WHERE id=?", (r["id"],)).fetchone())


def ustaw_uwage(w: str, uwaga: str, *, zrodlo: str = "manual", teraz: datetime | None = None,
                sciezka: Path | None = None) -> dict:
    """FR-11 `/fokus`: nowy wpis z osiami ostatniego wpisu z dziś (tryb dnia bez zmian, zostaje pora zmiany).
    Bez dzisiejszego wpisu nie ma osi do skopiowania → `brak_wpisu` (Bibo zaczyna od siatki)."""
    w = _wymagaj_wlasciciela(w)
    _wybor("uwaga", uwaga, UWAGA)
    _wybor("zrodlo", zrodlo, ZRODLA)
    teraz = teraz or kontakt.teraz()
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            r = _ostatni_dzis(db, w, teraz)
            if not r:
                raise BladStanu("brak_wpisu", "Najpierw wpis na siatce — bez niego nie ma trybu dnia.")
            wid = "w_" + secrets.token_hex(6)
            db.execute("INSERT INTO wpisy_stanu (id, wlasciciel, utworzono, energia, przyjemnosc, cwiartka, uwaga, zrodlo) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (wid, w, _utc(teraz), r["energia"], r["przyjemnosc"], r["cwiartka"], uwaga, zrodlo))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        return dict(db.execute("SELECT * FROM wpisy_stanu WHERE id=?", (wid,)).fetchone())


def _ostatni_dzis(db: sqlite3.Connection, w: str, teraz: datetime) -> sqlite3.Row | None:
    od, do = _dzien_utc(teraz)
    return db.execute("SELECT * FROM wpisy_stanu WHERE wlasciciel=? AND utworzono>=? AND utworzono<? "
                      "ORDER BY utworzono DESC, rowid DESC LIMIT 1", (w, od, do)).fetchone()


def dzisiejszy(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> dict | None:
    """Ostatni wpis z dziś: jego `cwiartka` to tryb dnia, `uwaga` to stan uwagi."""
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        r = _ostatni_dzis(db, w, teraz or kontakt.teraz())
        return dict(r) if r else None


def tydzien(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> list[dict]:
    """Ostatnie 7 dni (dziś jako ostatni) po jednym zapytaniu: [{dzien, cwiartka, uwaga} | brak]."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    z = kontakt.strefa()
    od, _ = _dzien_utc(teraz, -6)
    _, do = _dzien_utc(teraz)
    with closing(_polacz(sciezka)) as db:
        wpisy = db.execute("SELECT utworzono, cwiartka, uwaga FROM wpisy_stanu WHERE wlasciciel=? AND utworzono>=? AND utworzono<? "
                           "ORDER BY utworzono, rowid", (w, od, do)).fetchall()
    ostatni = {}
    for r in wpisy:   # późniejszy wpis dnia nadpisuje wcześniejszy
        ostatni[datetime.fromisoformat(r["utworzono"]).astimezone(z).date()] = (r["cwiartka"], r["uwaga"])
    dzis = teraz.astimezone(z).date()
    wynik = []
    for i in range(6, -1, -1):
        d = dzis - timedelta(days=i)
        c, u = ostatni.get(d, (None, None))
        wynik.append({"dzien": d.isoformat(), "cwiartka": c, "uwaga": u})
    return wynik


def czy_pokazac_siatke(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> bool:
    """FR-1: True najwyżej raz dziennie i tylko, gdy dziś nie ma jeszcze wpisu. Zapis „pokazano”
    następuje razem ze sprawdzeniem, więc kolejna tura tego samego dnia nie powtarza siatki
    (ignorowana siatka nie wraca tego dnia: brak ponagleń, FR-6)."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    dzien = teraz.astimezone(kontakt.strefa()).date()
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            pokazac = _ostatni_dzis(db, w, teraz) is None and db.execute(
                "SELECT 1 FROM siatka_pokazana WHERE wlasciciel=? AND dzien=?", (w, dzien.isoformat())).fetchone() is None
            if pokazac:
                db.execute("INSERT INTO siatka_pokazana (wlasciciel, dzien) VALUES (?,?)", (w, dzien.isoformat()))
                db.execute("DELETE FROM siatka_pokazana WHERE dzien<?", ((dzien - timedelta(days=DNI_POKAZU)).isoformat(),))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return pokazac


# --- sygnały gorszego dnia / uwagi ------------------------------------------------

def zapisz_sygnal(w: str, rodzaj: str, cel: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> dict:
    w = _wymagaj_wlasciciela(w)
    _wybor("rodzaj", rodzaj, RODZAJE)
    _wybor("cel", cel, CELE)
    sid = "g_" + secrets.token_hex(6)
    with closing(_polacz(sciezka)) as db:
        db.execute("INSERT INTO sygnaly_stanu (id, wlasciciel, utworzono, rodzaj, cel) VALUES (?,?,?,?,?)",
                   (sid, w, _utc(teraz or kontakt.teraz()), rodzaj, cel))
        return dict(db.execute("SELECT * FROM sygnaly_stanu WHERE id=?", (sid,)).fetchone())


def pytano_dzis(w: str, cel: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> bool:
    """Czy dziś zadano już pytanie o ten cel (FR-5: najwyżej jedno dziennie)."""
    w = _wymagaj_wlasciciela(w)
    _wybor("cel", cel, CELE)
    od, do = _dzien_utc(teraz or kontakt.teraz())
    with closing(_polacz(sciezka)) as db:
        return db.execute("SELECT 1 FROM sygnaly_stanu WHERE wlasciciel=? AND cel=? AND zapytano=1 AND utworzono>=? AND utworzono<? LIMIT 1",
                          (w, cel, od, do)).fetchone() is not None


def oznacz_pytanie(w: str, sygnal_id: str, *, sciezka: Path | None = None) -> None:
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        n = db.execute("UPDATE sygnaly_stanu SET zapytano=1 WHERE id=? AND wlasciciel=?", (sygnal_id, w)).rowcount
    if n == 0:
        raise BladStanu("brak_wpisu", "Nie ma takiego sygnału.")


def odpowiedz_na_pytanie(w: str, sygnal_id: str, potwierdzone: bool, *, sciezka: Path | None = None) -> None:
    """Zapisuje odpowiedź przy sygnale. Nie tworzy wpisu stanu: zmianę po „tak” robi osobny, jawny krok."""
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        n = db.execute("UPDATE sygnaly_stanu SET potwierdzone=? WHERE id=? AND wlasciciel=? AND zapytano=1",
                       (int(bool(potwierdzone)), sygnal_id, w)).rowcount
    if n == 0:
        raise BladStanu("brak_wpisu", "Nie ma zadanego pytania dla tego sygnału.")
