"""Pliki danych wtyczki w `$HERMES_HOME/local/bibo_tryby/` (przeżywają aktualizacje)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DOMYSLNE_USTAWIENIA = {
    "tryby": ["detektyw"],
    "port": 8787,
    "url_staly": None,          # gdy ustawiony — tunel się nie uruchamia
    "propozycje_dziennie": 1,
    "kontrola_min": 10,
    "limit_haiku_na_godzine": 30,
    "strefa": "Europe/Warsaw",
}


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
