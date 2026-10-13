"""Pliki danych wtyczki w `$HERMES_HOME/local/bibo_tryby/` (przeżywają aktualizacje)."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DOMYSLNE_USTAWIENIA = {
    "strefa": "Europe/Warsaw",
    "stan": True,               # wpisy stanu dnia (siatka w rozmowie); false = Bibo nic nie pokazuje ani nie przechwytuje
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
