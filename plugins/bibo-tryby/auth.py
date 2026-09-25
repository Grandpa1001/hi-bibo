"""Weryfikacja danych z Telegram Mini App (`initData`) i lista dozwolonych userów.

Telegram podpisuje `initData` tokenem bota (HMAC-SHA256), więc zweryfikować je
może tylko instalacja, która ma ten token — każdy user ma własnego bota.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl


class BladAuth(Exception):
    """Kod błędu dla API: "podpis" albo "uzytkownik"."""


def weryfikuj_init_data(raw: str, token: str, max_wiek: int = 3600, teraz: float | None = None) -> dict:
    """Zwraca obiekt `user` z `initData`, jeśli podpis i wiek są poprawne."""
    try:
        pola = dict(parse_qsl(raw or "", keep_blank_values=True, strict_parsing=True))
    except ValueError:
        raise BladAuth("podpis")
    podany = pola.pop("hash", "")
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(pola.items()))  # wszystkie pola poza hash
    sekret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    wyliczony = hmac.new(sekret, dcs.encode(), hashlib.sha256).hexdigest()
    if not podany or not token or not hmac.compare_digest(wyliczony, podany):
        raise BladAuth("podpis")
    try:
        wiek = (teraz if teraz is not None else time.time()) - int(pola.get("auth_date", "0"))
        user = json.loads(pola["user"])
    except (ValueError, KeyError):
        raise BladAuth("podpis")
    if wiek > max_wiek:
        raise BladAuth("podpis")
    return user


def dozwoleni() -> set[str]:
    raw = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    return {x.strip() for x in raw.replace(";", ",").split(",") if x.strip()}


def sprawdz_usera(user: dict) -> str:
    uid = str(user.get("id", ""))
    lista = dozwoleni()
    if not uid or ("*" not in lista and uid not in lista):
        raise BladAuth("uzytkownik")
    return uid
