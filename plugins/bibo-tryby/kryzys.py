"""Treści o samookaleczeniu i myślach samobójczych: bezpieczeństwo ma pierwszeństwo przed planowaniem.

Działa w kodzie, bez modelu i niezależnie od ustawienia `stan`: gdy wiadomość usera pasuje do wzorców,
wtyczka sama wysyła numery pomocy (116 123 — Kryzysowy Telefon Zaufania, 112), a w tej turze model dostaje
polecenie przerwania planowania. Do końca doby Bibo nie pokazuje siatki, nie zadaje pytań o stan i nie
przypomina o przerwach — nic nie wygląda jak „kolejny punkt do odhaczenia”. Treści wiadomości nie są
nigdzie zapisywane; pamiętamy tylko, że dziś padły (w pamięci procesu).

Wzorce są celowo szerokie: lepiej raz niepotrzebnie podać numer niż przeoczyć prawdziwy kryzys.
Nie diagnozujemy i nie nazywamy stanu klinicznie.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date, datetime

from . import kontakt

log = logging.getLogger("bibo-tryby")

NUMERY = "116 123 (Kryzysowy Telefon Zaufania) lub 112"

WIADOMOSC = ("Słyszę, że jest Ci teraz bardzo ciężko, i cieszę się, że mi o tym piszesz. "
             "Nie musisz zostawać z tym w pojedynkę. Jeśli myślisz o zrobieniu sobie krzywdy, zadzwoń teraz: "
             f"{NUMERY}, a jeśli jesteś w bezpośrednim niebezpieczeństwie — 112. "
             "Jestem tutaj. Dziś nie planujemy niczego, chyba że sam do tego wrócisz.")

KONTEKST_TURY = ("BEZPIECZEŃSTWO: user napisał o myślach samobójczych lub samookaleczeniu. Przerwij tryb planowania: "
                 "nie proponuj zadań, kroków, trybów ani check-inów, nie oceniaj i nie diagnozuj. Odpowiedz ciepło, krótko, "
                 f"zapytaj, czy jest teraz w bezpiecznym miejscu, i zachęć do kontaktu: {NUMERY}. "
                 "Zrób to nawet jeśli osobna wiadomość z numerami już poszła.")
KONTEKST_DNIA = ("BEZPIECZEŃSTWO: dziś padły treści o kryzysie. Nie planuj dnia i nie proponuj zadań, dopóki user sam do tego nie wróci. "
                 "Bądź obecny, krótko i ciepło.")

_WZORCE = [re.compile(p) for p in (
    r"\bzabic sie\b(?! ze smiech| z nudow| ze wstydu)", r"\bsie zabic\b(?! ze smiech| z nudow| ze wstydu)", r"\bzabij\w* sie\b", r"\bzabil\w* sie\b(?! ze smiech)", r"\bchc\w* sie zabic\b",
    r"\bnie chc\w* (juz )?zyc\b", r"\bnie chce mi sie zyc\b", r"\bnie warto (juz )?zyc\b", r"\bwolal\w* nie zyc\b",
    r"\bchc\w* umrzec\b", r"\bsamobojstw", r"\bsamobojcz", r"\bskonczyc ze soba\b", r"\bodebrac sobie zycie\b",
    r"\btargn\w* sie na (swoje )?zycie\b", r"\bsamookalecz", r"\b(pociac|ciac) sie\b", r"\bsie (pociac|ciac)\b", r"\btne sie\b",
    r"\b(s)?krzywdz\w* sie\b", r"\bzrob\w* sobie krzywd",
)]

# Doba, w której padły treści kryzysowe, i flaga „ta tura” (jednorazowa).
_dzien: dict[str, date] = {}
_tura: set[str] = set()


def _norm(tekst: str) -> str:
    t = unicodedata.normalize("NFKD", (tekst or "").lower().replace("ł", "l"))
    return "".join(c for c in t if not unicodedata.combining(c))


def wykryj(tekst: str) -> bool:
    t = _norm(tekst)
    return any(p.search(t) for p in _WZORCE)


def _dzis() -> date:
    return kontakt.teraz().astimezone(kontakt.strefa()).date()


def zanotuj(uid: str) -> None:
    """Pamięta, że u tego usera dziś padły treści kryzysowe, i że kolejna tura wymaga polecenia bezpieczeństwa."""
    _dzien[str(uid)] = _dzis()
    _tura.add(str(uid))


def aktywny(uid: str | None = None) -> bool:
    """Czy dziś padły treści kryzysowe (dla `uid`, a bez niego dla kogokolwiek)."""
    dzis = _dzis()
    if uid is not None:
        return _dzien.get(str(uid)) == dzis
    return any(d == dzis for d in _dzien.values())


def kontekst(uid: str) -> str | None:
    """Linia do kontekstu tury: pełne polecenie w turze zaraz po wiadomości, potem łagodniejsza do końca doby."""
    uid = str(uid)
    if uid in _tura:
        _tura.discard(uid)
        return KONTEKST_TURY
    return KONTEKST_DNIA if aktywny(uid) else None


async def wyslij(uid: str, uslugi) -> bool:
    """Numery pomocy jako osobna wiadomość, bez klawiatury i bez żadnych przycisków planowania."""
    if not getattr(uslugi, "bot", None):
        return False
    try:
        await uslugi.bot.wywolaj("sendMessage", {"chat_id": uid, "text": WIADOMOSC})
        return True
    except Exception as e:
        log.warning("bibo-tryby: wiadomość kryzysowa nie wysłana: %s", type(e).__name__)
        return False
