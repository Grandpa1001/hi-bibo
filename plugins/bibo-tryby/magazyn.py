"""Pliki danych wtyczki w `$HERMES_HOME/local/bibo_tryby/` (przeżywają aktualizacje)."""
from __future__ import annotations

import json
import os
import secrets
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

DOMYSLNE_USTAWIENIA = {
    "tryby": ["detektyw"],
    "port": 8787,
    "url_staly": None,          # gdy ustawiony — tunel się nie uruchamia
    "propozycje_dziennie": 1,
    "kontrola_min": 10,
    "limit_haiku_na_godzine": 30,
    "strefa": "Europe/Warsaw",
    "stan": True,               # wpisy stanu dnia (siatka w rozmowie); false = Bibo nic nie pokazuje ani nie przechwytuje
}

PODEJRZANI_STARTOWI = [
    ("Perfekcjonista", "🎩"),
    ("Jutrzejszy Ja", "📅"),
    ("Research Bez Dna", "🔎"),
    ("Brak Paliwa", "🔋"),
    ("Mgła Startowa", "🌫️"),
    ("Czarnowidz", "🌧️"),
]
MAKS_PODEJRZANYCH = 20
WYGASNIECIE_MIN = 30                 # sprawa bez `zamknij` → usuwana po tylu minutach
ID_HEX = 4                           # długość losowego ID sprawy: `s_<hex>`


def hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def katalog() -> Path:
    k = hermes_home() / "local" / "bibo_tryby"
    k.mkdir(parents=True, exist_ok=True)
    return k


def czytaj(nazwa: str, domyslne=None):
    p = katalog() / nazwa
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return domyslne


def zapisz(nazwa: str, dane) -> None:
    """Zapis atomowy: plik tymczasowy + os.replace."""
    k = katalog()
    fd, tmp = tempfile.mkstemp(dir=k, prefix=f".{nazwa}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dane, f, ensure_ascii=False, indent=2)
    os.replace(tmp, k / nazwa)


def ustawienia() -> dict:
    return {**DOMYSLNE_USTAWIENIA, **(czytaj("ustawienia.json", {}) or {})}


# --- czas ---------------------------------------------------------------------

def _strefa():
    nazwa = ustawienia().get("strefa") or "Europe/Warsaw"
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(nazwa)
    except Exception:
        return timezone.utc


def teraz(dt: datetime | None = None) -> datetime:
    return (dt or datetime.now(tz=timezone.utc)).astimezone(_strefa())


def iso(dt: datetime | None = None) -> str:
    return teraz(dt).isoformat(timespec="seconds")


def data(dt: datetime | None = None) -> str:
    return teraz(dt).date().isoformat()


# --- kartoteka ----------------------------------------------------------------

def _pusta_kartoteka() -> dict:
    return {
        "wersja": 1,
        "nastepny_numer": 1,
        "podejrzani": {n: {"emoji": e, "zatrzymania": 0, "obalone": 0, "ruszylo": 0, "ostatnio": None}
                       for n, e in PODEJRZANI_STARTOWI},
        "sprawy": [],
        "propozycje": {},
        "notatka_dla_bibo": None,
    }


def kartoteka() -> dict:
    k = czytaj("kartoteka.json", None)
    if not isinstance(k, dict):
        k = _pusta_kartoteka()
        zapisz("kartoteka.json", k)
        return k
    # miękkie uzupełnienie brakujących kluczy po aktualizacji schematu
    baza = _pusta_kartoteka()
    for klucz, wart in baza.items():
        k.setdefault(klucz, wart)
    for n, e in PODEJRZANI_STARTOWI:
        k["podejrzani"].setdefault(n, {"emoji": e, "zatrzymania": 0, "obalone": 0, "ruszylo": 0, "ostatnio": None})
    return k


def zapisz_kartoteke(k: dict) -> None:
    zapisz("kartoteka.json", k)


def znani_podejrzani(k: dict) -> list[tuple[str, str]]:
    return [(n, d.get("emoji", "🌫️")) for n, d in k["podejrzani"].items()]


# --- sprawy (aktywne + czekające na kontrolę) --------------------------------

def sprawy() -> dict:
    return czytaj("sprawy.json", {}) or {}


def zapisz_sprawy(s: dict) -> None:
    zapisz("sprawy.json", s)


def nowe_id() -> str:
    return "s_" + secrets.token_hex(ID_HEX // 2 + ID_HEX % 2)[:ID_HEX]


def wygas_stare(s: dict, granica: datetime | None = None) -> list[str]:
    """Usuwa niezamknięte sprawy starsze niż WYGASNIECIE_MIN — zwraca ich id."""
    granica = granica or teraz()
    prog = granica - timedelta(minutes=WYGASNIECIE_MIN)
    usuniete = []
    for sid, sprawa in list(s.items()):
        etap = sprawa.get("etap")
        if etap == "zamknieta":
            continue
        try:
            ostatnia = datetime.fromisoformat(sprawa.get("ostatnia_akcja") or "")
        except ValueError:
            usuniete.append(sid)
            del s[sid]
            continue
        if ostatnia.astimezone(_strefa()) < prog:
            usuniete.append(sid)
            del s[sid]
    return usuniete


def aktywna_sprawa(s: dict, uid: str) -> dict | None:
    for sid, sprawa in s.items():
        if str(sprawa.get("user")) == uid and sprawa.get("etap") != "zamknieta":
            return {"id": sid, **sprawa}
    return None


# --- limit wywołań Haiku (30/h per user) --------------------------------------

def sprawdz_i_zapisz_limit(uid: str, teraz_ts: float | None = None) -> bool:
    """True gdy wywołanie mieści się w limicie i zostaje zapisane; False = przekroczony."""
    teraz_ts = teraz_ts if teraz_ts is not None else time.time()
    limit = int(ustawienia().get("limit_haiku_na_godzine", 30))
    stan = czytaj("limity.json", {}) or {}
    lista = [t for t in stan.get(uid, []) if teraz_ts - t < 3600]
    if len(lista) >= limit:
        stan[uid] = lista
        zapisz("limity.json", stan)
        return False
    lista.append(teraz_ts)
    stan[uid] = lista
    # sprzątanie nieaktywnych userów
    stan = {u: [t for t in ts if teraz_ts - t < 3600] for u, ts in stan.items()}
    stan = {u: ts for u, ts in stan.items() if ts}
    zapisz("limity.json", stan)
    return True
