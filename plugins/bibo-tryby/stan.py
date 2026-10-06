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
import time
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import karta, kontakt, magazyn

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
CREATE TABLE IF NOT EXISTS wiadomosci_dl (
    wlasciciel TEXT NOT NULL,
    utworzono TEXT NOT NULL,
    dl INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS wiadomosci_dl_czas ON wiadomosci_dl (wlasciciel, utworzono);
CREATE TABLE IF NOT EXISTS oszacowania (
    wlasciciel TEXT NOT NULL,
    dzien TEXT NOT NULL,
    cwiartka TEXT NOT NULL,
    energia INTEGER NOT NULL,
    przyjemnosc INTEGER NOT NULL,
    odpowiedz INTEGER,
    PRIMARY KEY (wlasciciel, dzien)
);
CREATE TABLE IF NOT EXISTS wsparcie (
    wlasciciel TEXT NOT NULL,
    dzien TEXT NOT NULL,
    PRIMARY KEY (wlasciciel, dzien)
);
CREATE TABLE IF NOT EXISTS podsumowania (
    wlasciciel TEXT NOT NULL,
    tydzien TEXT NOT NULL,
    PRIMARY KEY (wlasciciel, tydzien)
);
CREATE TABLE IF NOT EXISTS kronika (
    id TEXT PRIMARY KEY,
    wlasciciel TEXT NOT NULL,
    utworzono TEXT NOT NULL,
    rodzaj TEXT NOT NULL,
    tekst TEXT NOT NULL,
    dane TEXT
);
CREATE INDEX IF NOT EXISTS kronika_czas ON kronika (wlasciciel, utworzono);
CREATE TABLE IF NOT EXISTS przypomnienia_uwagi (
    wlasciciel TEXT NOT NULL,
    dzien TEXT NOT NULL,
    ostatnie TEXT NOT NULL,
    liczba INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (wlasciciel, dzien)
);
CREATE TABLE IF NOT EXISTS aktywnosc (
    wlasciciel TEXT NOT NULL,
    dzien TEXT NOT NULL,
    tury INTEGER NOT NULL DEFAULT 0,
    sesje INTEGER NOT NULL DEFAULT 0,
    sekundy INTEGER NOT NULL DEFAULT 0,
    start_sesji TEXT NOT NULL,
    ostatnia TEXT NOT NULL,
    PRIMARY KEY (wlasciciel, dzien)
);
"""
_gotowe: set[str] = set()   # bazy ze świeżo sprawdzonym schematem: nie powtarzamy go przy każdej turze
DNI_POKAZU = 14
PRZERWA_SESJI_MIN = 30       # dłuższa przerwa między turami zaczyna nową sesję
DNI_AKTYWNOSCI = 60
DNI_DLUGOSCI = 30
DNI_BAZY_DLUGOSCI = 14
PRZYPOMNIENIE_CO_MIN = 90      # FR-14: w hiperfokusie najwyżej jedno przypomnienie na 90 min
MAKS_PRZYPOMNIEN = 6           # dziennie; twardy bezpiecznik, żeby nie zasypać


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
    """FR-11 `/fokus`: nowy wpis z osiami, słowem i notatką ostatniego wpisu z dziś (tryb dnia bez zmian, zostaje pora zmiany).
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
            db.execute("INSERT INTO wpisy_stanu (id, wlasciciel, utworzono, energia, przyjemnosc, cwiartka, uwaga, slowo, notatka, zrodlo) "
                       "VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (wid, w, _utc(teraz), r["energia"], r["przyjemnosc"], r["cwiartka"], uwaga, r["slowo"], r["notatka"], zrodlo))
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


# --- aktywność w tle (FR-10) ---------------------------------------------------------

def rejestruj_ture(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> dict | None:
    """Wołane raz na turę właściciela: jedno połączenie i jedna krótka transakcja. Liczy tylko
    znaczniki czasu (tury, sesje, czas), nigdy treść rozmowy. Zwraca dzisiejszy wpis stanu
    (jego `cwiartka` to tryb dnia), żeby hook nie otwierał bazy drugi raz."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    dzien = teraz.astimezone(kontakt.strefa()).date()
    t = _utc(teraz)
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            r = db.execute("SELECT * FROM aktywnosc WHERE wlasciciel=? AND dzien=?", (w, dzien.isoformat())).fetchone()
            if not r:
                db.execute("INSERT INTO aktywnosc (wlasciciel, dzien, tury, sesje, sekundy, start_sesji, ostatnia) "
                           "VALUES (?,?,1,1,0,?,?)", (w, dzien.isoformat(), t, t))
                db.execute("DELETE FROM aktywnosc WHERE dzien<?", ((dzien - timedelta(days=DNI_AKTYWNOSCI)).isoformat(),))
            else:
                przerwa = int((teraz - datetime.fromisoformat(r["ostatnia"])).total_seconds())
                if przerwa > PRZERWA_SESJI_MIN * 60:
                    db.execute("UPDATE aktywnosc SET tury=tury+1, sesje=sesje+1, start_sesji=?, ostatnia=? WHERE wlasciciel=? AND dzien=?",
                               (t, t, w, dzien.isoformat()))
                else:
                    db.execute("UPDATE aktywnosc SET tury=tury+1, sekundy=sekundy+?, ostatnia=? WHERE wlasciciel=? AND dzien=?",
                               (max(przerwa, 0), t, w, dzien.isoformat()))
            wpis = _ostatni_dzis(db, w, teraz)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        return dict(wpis) if wpis else None


def zaangazowanie(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None,
                  sciezka_karty: Path | None = None) -> dict:
    """FR-10: zaangażowanie dnia z aktywności, bez pytania usera. `domkniecia` to karty spraw zakończone
    tego dnia; zewnętrznych issues ta instancja nie widzi."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    z = kontakt.strefa()
    dzien = teraz.astimezone(z).date()
    with closing(_polacz(sciezka)) as db:
        r = db.execute("SELECT tury, sesje, sekundy FROM aktywnosc WHERE wlasciciel=? AND dzien=?",
                       (w, dzien.isoformat())).fetchone()
    domkniecia = sum(1 for k in karta.odczytaj(w, status="zakonczona", sciezka=sciezka_karty)
                     if datetime.fromisoformat(k["zaktualizowano"]).astimezone(z).date() == dzien)
    return {"dzien": dzien.isoformat(), "tury": r["tury"] if r else 0, "sesje": r["sesje"] if r else 0,
            "minuty": (r["sekundy"] // 60) if r else 0, "domkniecia": domkniecia}


def zajmij_przypomnienie(w: str, *, wstrzymane: bool = False, teraz: datetime | None = None,
                         sciezka: Path | None = None) -> bool:
    """FR-14 (hiperfokus): atomowo „bierze” przypomnienie o przerwie i zwraca True, gdy trzeba je wysłać.
    Warunki: dziś ostatni wpis ma uwagę hyperfocus, od niego i od poprzedniego przypomnienia minęło
    ≥ PRZYPOMNIENIE_CO_MIN, a dzienny limit nie wyczerpany. Zajęcie następuje PRZED wysyłką, więc
    awaria wysyłki nie powoduje powtórki. `wstrzymane` (pauza/cisza) zużywa termin bez wysyłki i bez
    liczenia do limitu: zaległe przypomnienie nie wychodzi po końcu ciszy."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    dzien = teraz.astimezone(kontakt.strefa()).date().isoformat()
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            e = _ostatni_dzis(db, w, teraz)
            wyslac = False
            if e and e["uwaga"] == "hyperfocus":
                r = db.execute("SELECT * FROM przypomnienia_uwagi WHERE wlasciciel=? AND dzien=?", (w, dzien)).fetchone()
                baza = datetime.fromisoformat(e["utworzono"])
                if r:
                    baza = max(baza, datetime.fromisoformat(r["ostatnie"]))
                if teraz - baza >= timedelta(minutes=PRZYPOMNIENIE_CO_MIN) and not (r and r["liczba"] >= MAKS_PRZYPOMNIEN):
                    wyslac = not wstrzymane
                    db.execute("INSERT INTO przypomnienia_uwagi (wlasciciel, dzien, ostatnie, liczba) VALUES (?,?,?,?) "
                               "ON CONFLICT(wlasciciel, dzien) DO UPDATE SET ostatnie=excluded.ostatnie, liczba=liczba+excluded.liczba",
                               (w, dzien, _utc(teraz), int(wyslac)))
                    db.execute("DELETE FROM przypomnienia_uwagi WHERE dzien<?",
                               ((teraz.astimezone(kontakt.strefa()).date() - timedelta(days=DNI_POKAZU)).isoformat(),))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return wyslac


# --- tempo pisania, sesja, historia (wejście dla sygnałów) ---------------------------------

def zapisz_dlugosc(w: str, dlugosc: int, *, teraz: datetime | None = None, sciezka: Path | None = None) -> dict:
    """Zapisuje samą długość wiadomości (nie treść) i zwraca porównanie z typowym tempem usera:
    `dzis` = średnia z 3 ostatnich dzisiejszych wiadomości (None, gdy mniej niż 3), `baza` = średnia
    z poprzednich dni (None, gdy mniej niż 20 wiadomości)."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    od, do = _dzien_utc(teraz)
    od_bazy, _ = _dzien_utc(teraz, -DNI_BAZY_DLUGOSCI)
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            db.execute("INSERT INTO wiadomosci_dl (wlasciciel, utworzono, dl) VALUES (?,?,?)", (w, _utc(teraz), int(dlugosc)))
            db.execute("DELETE FROM wiadomosci_dl WHERE utworzono<?", (_dzien_utc(teraz, -DNI_DLUGOSCI)[0],))
            ost = [r[0] for r in db.execute("SELECT dl FROM wiadomosci_dl WHERE wlasciciel=? AND utworzono>=? AND utworzono<? "
                                            "ORDER BY utworzono DESC, rowid DESC LIMIT 3", (w, od, do))]
            n, suma = db.execute("SELECT COUNT(*), COALESCE(SUM(dl),0) FROM wiadomosci_dl WHERE wlasciciel=? AND utworzono>=? AND utworzono<?",
                                 (w, od_bazy, od)).fetchone()
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return {"dzis": sum(ost) / 3 if len(ost) == 3 else None, "baza": suma / n if n >= 20 else None}


def sesja(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> dict | None:
    """Dzisiejsza aktywność: początek bieżącej sesji, liczba sesji i łączny czas w sesjach (sekundy)."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    dzien = teraz.astimezone(kontakt.strefa()).date().isoformat()
    with closing(_polacz(sciezka)) as db:
        r = db.execute("SELECT start_sesji, ostatnia, sesje, sekundy FROM aktywnosc WHERE wlasciciel=? AND dzien=?", (w, dzien)).fetchone()
    return dict(r) if r else None


def dni_bez_wpisu(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> tuple[str | None, int | None]:
    """(data ostatniego wpisu usera, ile dni temu) — (None, None), gdy nigdy nie było wpisu."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    z = kontakt.strefa()
    with closing(_polacz(sciezka)) as db:
        r = db.execute("SELECT utworzono FROM wpisy_stanu WHERE wlasciciel=? ORDER BY utworzono DESC LIMIT 1", (w,)).fetchone()
    if not r:
        return None, None
    d = datetime.fromisoformat(r[0]).astimezone(z).date()
    return d.isoformat(), (teraz.astimezone(z).date() - d).days


def _ostatnie_wpisy_dni(db: sqlite3.Connection, w: str, teraz: datetime, dni: int) -> list[sqlite3.Row]:
    """Ostatni wpis z każdego z `dni` ostatnich dób (włącznie z dziś), od najstarszego."""
    z = kontakt.strefa()
    od, _ = _dzien_utc(teraz, -(dni - 1))
    po_dniach: dict = {}
    for r in db.execute("SELECT * FROM wpisy_stanu WHERE wlasciciel=? AND utworzono>=? ORDER BY utworzono, rowid", (w, od)):
        po_dniach[datetime.fromisoformat(r["utworzono"]).astimezone(z).date()] = r
    return [po_dniach[d] for d in sorted(po_dniach)]


def typowy_stan(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> dict | None:
    """FR-6: oszacowanie bez pytania usera — najczęstsza ćwiartka z ostatnich 7 dób z wpisem (remis: nowsza),
    z osiami najnowszego wpisu w tej ćwiartce. None, gdy w ostatnim tygodniu nie było wpisów."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    with closing(_polacz(sciezka)) as db:
        wpisy = _ostatnie_wpisy_dni(db, w, teraz, 14)[-7:]
    if not wpisy:
        return None
    licz = {}
    for r in wpisy:
        licz[r["cwiartka"]] = licz.get(r["cwiartka"], 0) + 1
    naj = max(licz.values())
    for r in reversed(wpisy):   # remis rozstrzyga najnowszy
        if licz[r["cwiartka"]] == naj:
            return {"cwiartka": r["cwiartka"], "energia": r["energia"], "przyjemnosc": r["przyjemnosc"]}
    return None


def regeneracja_z_rzedu(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> int:
    """Ile kolejnych dób (kończąc na dziś albo, bez dzisiejszego wpisu, na wczoraj) ostatni wpis dnia to Regeneracja."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    z = kontakt.strefa()
    with closing(_polacz(sciezka)) as db:
        wpisy = _ostatnie_wpisy_dni(db, w, teraz, 30)
    po_dniach = {datetime.fromisoformat(r["utworzono"]).astimezone(z).date(): r["cwiartka"] for r in wpisy}
    d = teraz.astimezone(z).date()
    if d not in po_dniach:
        d -= timedelta(days=1)
    n = 0
    while po_dniach.get(d) == "recovery":
        n += 1
        d -= timedelta(days=1)
    return n


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


def sygnaly_dzis(w: str, cel: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> list[dict]:
    w = _wymagaj_wlasciciela(w)
    _wybor("cel", cel, CELE)
    od, do = _dzien_utc(teraz or kontakt.teraz())
    with closing(_polacz(sciezka)) as db:
        return [dict(r) for r in db.execute("SELECT * FROM sygnaly_stanu WHERE wlasciciel=? AND cel=? AND utworzono>=? AND utworzono<? "
                                            "ORDER BY utworzono", (w, cel, od, do))]


def zapisz_sygnal_raz_dziennie(w: str, rodzaj: str, cel: str, *, teraz: datetime | None = None,
                               sciezka: Path | None = None) -> bool:
    """Ten sam rodzaj sygnału dla tego samego celu liczy się raz na dobę (nie mnożymy dowodów z jednej cechy)."""
    teraz = teraz or kontakt.teraz()
    if any(r["rodzaj"] == rodzaj for r in sygnaly_dzis(w, cel, teraz=teraz, sciezka=sciezka)):
        return False
    zapisz_sygnal(w, rodzaj, cel, teraz=teraz, sciezka=sciezka)
    return True


def stan_pytan(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> dict:
    """Wszystko, czego po turze potrzebuje wykrywanie, w jednym połączeniu z bazą:
    `sygnaly` (dzisiejsze wiersze), `zapytane` (cele, o które dziś pytano), `oczekuje` (jest pytanie bez odpowiedzi)
    i `pytan` (liczba dzisiejszych pytań, także oszacowań)."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    od, do = _dzien_utc(teraz)
    dzien = teraz.astimezone(kontakt.strefa()).date().isoformat()
    with closing(_polacz(sciezka)) as db:
        wiersze = [dict(r) for r in db.execute("SELECT * FROM sygnaly_stanu WHERE wlasciciel=? AND utworzono>=? AND utworzono<? ORDER BY utworzono",
                                               (w, od, do))]
        osz = db.execute("SELECT odpowiedz FROM oszacowania WHERE wlasciciel=? AND dzien=?", (w, dzien)).fetchone()
    zapytane = {r["cel"] for r in wiersze if r["zapytano"]}
    return {"sygnaly": wiersze, "zapytane": zapytane,
            "oczekuje": any(r["zapytano"] and r["potwierdzone"] is None for r in wiersze) or (osz is not None and osz[0] is None),
            "pytan": len(zapytane) + (1 if osz is not None else 0)}


def pytan_dzis(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> int:
    """Liczba różnych celów, o które dziś już pytano (sygnały) plus dzisiejsze oszacowanie."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    od, do = _dzien_utc(teraz)
    dzien = teraz.astimezone(kontakt.strefa()).date().isoformat()
    with closing(_polacz(sciezka)) as db:
        n = db.execute("SELECT COUNT(DISTINCT cel) FROM sygnaly_stanu WHERE wlasciciel=? AND zapytano=1 AND utworzono>=? AND utworzono<?",
                       (w, od, do)).fetchone()[0]
        n += db.execute("SELECT COUNT(*) FROM oszacowania WHERE wlasciciel=? AND dzien=?", (w, dzien)).fetchone()[0]
    return n


def oznacz_pytanie_celu(w: str, cel: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> None:
    """Zaznacza, że o ten cel zapytano (wszystkie dzisiejsze sygnały celu)."""
    w = _wymagaj_wlasciciela(w)
    od, do = _dzien_utc(teraz or kontakt.teraz())
    with closing(_polacz(sciezka)) as db:
        db.execute("UPDATE sygnaly_stanu SET zapytano=1 WHERE wlasciciel=? AND cel=? AND utworzono>=? AND utworzono<?", (w, cel, od, do))


def oczekujace_pytanie(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> dict | None:
    """Zadane dziś, a jeszcze nieodpowiedziane pytanie: {"typ": "sygnal", "cel"} albo {"typ": "oszacowanie", ...}."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    od, do = _dzien_utc(teraz)
    dzien = teraz.astimezone(kontakt.strefa()).date().isoformat()
    with closing(_polacz(sciezka)) as db:
        r = db.execute("SELECT cel FROM sygnaly_stanu WHERE wlasciciel=? AND zapytano=1 AND potwierdzone IS NULL AND utworzono>=? AND utworzono<? "
                       "ORDER BY utworzono DESC LIMIT 1", (w, od, do)).fetchone()
        o = db.execute("SELECT * FROM oszacowania WHERE wlasciciel=? AND dzien=? AND odpowiedz IS NULL", (w, dzien)).fetchone()
    if o:   # oszacowanie i pytanie o sygnały nie występują razem (jedno pytanie naraz), więc kolejność nie ma znaczenia
        return {"typ": "oszacowanie", **{k: o[k] for k in ("cwiartka", "energia", "przyjemnosc")}}
    return {"typ": "sygnal", "cel": r["cel"]} if r else None


def odpowiedz_na_cel(w: str, cel: str, potwierdzone: bool, *, teraz: datetime | None = None, sciezka: Path | None = None) -> None:
    """Zapisuje odpowiedź przy wszystkich dzisiejszych, zadanych i nieodpowiedzianych sygnałach celu."""
    w = _wymagaj_wlasciciela(w)
    od, do = _dzien_utc(teraz or kontakt.teraz())
    with closing(_polacz(sciezka)) as db:
        db.execute("UPDATE sygnaly_stanu SET potwierdzone=? WHERE wlasciciel=? AND cel=? AND zapytano=1 AND potwierdzone IS NULL "
                   "AND utworzono>=? AND utworzono<?", (int(bool(potwierdzone)), w, cel, od, do))


def zapisz_oszacowanie(w: str, oszacowanie: dict, *, teraz: datetime | None = None, sciezka: Path | None = None) -> bool:
    """FR-6: najwyżej jedno oszacowanie na dobę. True, gdy zapisano (czyli można zapytać)."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    dzien = teraz.astimezone(kontakt.strefa()).date().isoformat()
    with closing(_polacz(sciezka)) as db:
        return db.execute("INSERT OR IGNORE INTO oszacowania (wlasciciel, dzien, cwiartka, energia, przyjemnosc) VALUES (?,?,?,?,?)",
                          (w, dzien, oszacowanie["cwiartka"], oszacowanie["energia"], oszacowanie["przyjemnosc"])).rowcount == 1


def czy_byla_propozycja_od(w: str, od_dnia: str | None, *, sciezka: Path | None = None) -> bool:
    """Czy po wskazanej dacie (ostatnim wpisie) proponowano już oszacowanie — jedna propozycja na przerwę."""
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        return db.execute("SELECT 1 FROM oszacowania WHERE wlasciciel=? AND dzien>? LIMIT 1", (w, od_dnia or "")).fetchone() is not None


def odpowiedz_na_oszacowanie(w: str, potwierdzone: bool, *, teraz: datetime | None = None, sciezka: Path | None = None) -> None:
    w = _wymagaj_wlasciciela(w)
    dzien = (teraz or kontakt.teraz()).astimezone(kontakt.strefa()).date().isoformat()
    with closing(_polacz(sciezka)) as db:
        db.execute("UPDATE oszacowania SET odpowiedz=? WHERE wlasciciel=? AND dzien=? AND odpowiedz IS NULL", (int(bool(potwierdzone)), w, dzien))


def potwierdzone_zle_dni(w: str, *, teraz: datetime | None = None, dni: int = 7, sciezka: Path | None = None) -> int:
    """Ile z ostatnich `dni` dób miało potwierdzony przez usera gorszy dzień (odpowiedź „tak” na pytanie)."""
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    z = kontakt.strefa()
    od, _ = _dzien_utc(teraz, -(dni - 1))
    with closing(_polacz(sciezka)) as db:
        rs = db.execute("SELECT utworzono FROM sygnaly_stanu WHERE wlasciciel=? AND cel='bad_day' AND potwierdzone=1 AND utworzono>=?", (w, od)).fetchall()
    return len({datetime.fromisoformat(r[0]).astimezone(z).date() for r in rs})


def wsparcie_niedawno(w: str, *, teraz: datetime | None = None, dni: int = 14, sciezka: Path | None = None) -> bool:
    w = _wymagaj_wlasciciela(w)
    teraz = teraz or kontakt.teraz()
    od = (teraz.astimezone(kontakt.strefa()).date() - timedelta(days=dni)).isoformat()
    with closing(_polacz(sciezka)) as db:
        return db.execute("SELECT 1 FROM wsparcie WHERE wlasciciel=? AND dzien>=? LIMIT 1", (w, od)).fetchone() is not None


def zapisz_wsparcie(w: str, *, teraz: datetime | None = None, sciezka: Path | None = None) -> None:
    w = _wymagaj_wlasciciela(w)
    dzien = (teraz or kontakt.teraz()).astimezone(kontakt.strefa()).date().isoformat()
    with closing(_polacz(sciezka)) as db:
        db.execute("INSERT OR IGNORE INTO wsparcie (wlasciciel, dzien) VALUES (?,?)", (w, dzien))


# --- podsumowanie tygodnia, Kronika, eksport i usuwanie (FR-9, FR-16, prywatność) ----------------

POWAZNOSC_UWAGI = {"hyperfocus": 2, "hypofocus": 1, "normal": 0}


def dni_tygodnia(w: str, koniec: date, *, dni: int = 7, sciezka: Path | None = None) -> list[dict]:
    """Okno `dni` dób kończące się na `koniec` (włącznie), od najstarszej. Dla każdej doby: ostatni tryb dnia (`cwiartka`),
    stan uwagi dnia (`uwaga`: hiperfokus, jeśli był choć raz, potem rozproszenie, inaczej norma) i godzina pierwszego
    zgłoszenia hiperfokusu (`start_hiper`, godzina lokalna). Doba bez wpisu ma wszystkie pola None. Jedno zapytanie."""
    w = _wymagaj_wlasciciela(w)
    z = kontakt.strefa()
    start = koniec - timedelta(days=dni - 1)
    od = _utc(datetime(start.year, start.month, start.day, tzinfo=z))
    do = _utc(datetime(koniec.year, koniec.month, koniec.day, tzinfo=z) + timedelta(days=1))
    with closing(_polacz(sciezka)) as db:
        wpisy = db.execute("SELECT utworzono, cwiartka, uwaga FROM wpisy_stanu WHERE wlasciciel=? AND utworzono>=? AND utworzono<? "
                           "ORDER BY utworzono, rowid", (w, od, do)).fetchall()
    po_dniach: dict[date, dict] = {}
    for r in wpisy:
        t = datetime.fromisoformat(r["utworzono"]).astimezone(z)
        d = po_dniach.setdefault(t.date(), {"cwiartka": None, "uwaga": "normal", "start_hiper": None})
        d["cwiartka"] = r["cwiartka"]
        if POWAZNOSC_UWAGI[r["uwaga"]] > POWAZNOSC_UWAGI[d["uwaga"]]:
            d["uwaga"] = r["uwaga"]
        if r["uwaga"] == "hyperfocus" and d["start_hiper"] is None:
            d["start_hiper"] = t.hour
    wynik = []
    for i in range(dni):
        d = start + timedelta(days=i)
        e = po_dniach.get(d)
        wynik.append({"dzien": d.isoformat(), **(e or {"cwiartka": None, "uwaga": None, "start_hiper": None})})
    return wynik


def zapisz_podsumowanie_tygodnia(w: str, tydzien: str, tekst: str, dane: str, *, teraz: datetime | None = None,
                                 sciezka: Path | None = None) -> bool:
    """Atomowo „zajmuje” tydzień ISO (np. 2026-W41) i zapisuje podsumowanie w Kronice. True tylko za pierwszym razem,
    więc to samo podsumowanie nie wyjdzie dwa razy, nawet przy równoległych turach."""
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            nowe = db.execute("INSERT OR IGNORE INTO podsumowania (wlasciciel, tydzien) VALUES (?,?)", (w, tydzien)).rowcount == 1
            if nowe:
                db.execute("INSERT INTO kronika (id, wlasciciel, utworzono, rodzaj, tekst, dane) VALUES (?,?,?,?,?,?)",
                           ("n_" + secrets.token_hex(6), w, _utc(teraz or kontakt.teraz()), "tydzien", tekst, dane))
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return nowe


def podsumowanie_juz_bylo(w: str, tydzien: str, *, sciezka: Path | None = None) -> bool:
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        return db.execute("SELECT 1 FROM podsumowania WHERE wlasciciel=? AND tydzien=?", (w, tydzien)).fetchone() is not None


def falszywe_alarmy(w: str, *, sciezka: Path | None = None) -> dict:
    """Metryka z dokumentu (cel ≤ 30%): ile odpowiedzi „nie” na pytania o stan i ile odpowiedzi w ogóle."""
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        r = db.execute("SELECT COUNT(DISTINCT substr(utworzono,1,10) || cel), "
                       "COUNT(DISTINCT CASE WHEN potwierdzone=0 THEN substr(utworzono,1,10) || cel END) "
                       "FROM sygnaly_stanu WHERE wlasciciel=? AND zapytano=1 AND potwierdzone IS NOT NULL", (w,)).fetchone()
    razem, nie = r[0], r[1]
    return {"razem": razem, "nie": nie, "odsetek": round(100 * nie / razem) if razem else None}


TABELE_DANYCH = ("wpisy_stanu", "sygnaly_stanu", "siatka_pokazana", "oszacowania", "wsparcie", "przypomnienia_uwagi",
                 "aktywnosc", "wiadomosci_dl", "podsumowania", "kronika")


def eksport(w: str, *, sciezka: Path | None = None) -> dict:
    """Wszystkie dane stanu właściciela w jednym słowniku (do pliku JSON). Bez treści rozmów, bo ich nie zapisujemy."""
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        tabele = {t: [dict(r) for r in db.execute(f"SELECT * FROM {t} WHERE wlasciciel=?", (w,))] for t in TABELE_DANYCH}
    return {"format": "bibo-stan-1", "wyeksportowano": _utc(kontakt.teraz()),
            "strefa": getattr(kontakt.strefa(), "key", "UTC"), "tabele": tabele,
            "metryki": {"falszywe_alarmy": falszywe_alarmy(w, sciezka=sciezka)}}


def policz_dane(w: str, *, sciezka: Path | None = None) -> dict[str, int]:
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        return {t: db.execute(f"SELECT COUNT(*) FROM {t} WHERE wlasciciel=?", (w,)).fetchone()[0] for t in TABELE_DANYCH}


def usun_wszystko(w: str, *, sciezka: Path | None = None) -> dict:
    """Kasuje wszystkie dane stanu właściciela jedną transakcją i czyści plik bazy, żeby usunięte wiersze nie zostały
    odzyskiwalne: `secure_delete` zeruje zwolnione strony, a checkpoint WAL (z kilkoma ponowieniami, bo blokuje go każdy
    równoległy czytelnik) i VACUUM usuwają ich kopie. Zwraca liczbę usuniętych wierszy po tabelach oraz
    `plik_wyczyszczony` (False, gdy WAL nie dał się obciąć — wtedy stare strony znikną przy kolejnych zapisach)."""
    w = _wymagaj_wlasciciela(w)
    with closing(_polacz(sciezka)) as db:
        db.execute("PRAGMA secure_delete=ON")
        db.execute("BEGIN IMMEDIATE")
        try:
            usuniete = {t: db.execute(f"DELETE FROM {t} WHERE wlasciciel=?", (w,)).rowcount for t in TABELE_DANYCH}
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        db.execute("PRAGMA busy_timeout=200")   # komenda działa w wątku gatewaya: czekamy krótko, nie 5 s na każdą próbę
        czysty = False
        for proba in range(3):
            if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0:   # 0 = nie zablokowany
                czysty = True
                break
            time.sleep(0.1)
        try:
            db.execute("VACUUM")
        except sqlite3.OperationalError:   # inny czytelnik trzyma bazę: dane z tabel i tak zniknęły
            czysty = False
    return {**usuniete, "plik_wyczyszczony": czysty}
