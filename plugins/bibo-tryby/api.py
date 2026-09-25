"""Trasy HTTP wtyczki. W M0: /health i strona diagnostyczna /spike."""
from __future__ import annotations

import asyncio
import html
import logging
from pathlib import Path

from aiohttp import web

from . import auth, gateway_most
from .telegram import BladTelegrama, EFEKT_KONFETTI, token

log = logging.getLogger("bibo-tryby")
ZASOBY = Path(__file__).parent / "zasoby"
WERSJA = "0.0.1"


def trasy(app: web.Application) -> None:
    app.router.add_get("/health", health)
    app.router.add_get("/", spike_strona)
    app.router.add_get("/spike", spike_strona)
    app.router.add_post("/api/spike/kto", spike_kto)
    app.router.add_post("/api/spike/haiku", spike_haiku)
    app.router.add_post("/api/spike/karta", spike_karta)
    app.router.add_post("/api/spike/bibo", spike_bibo)
    app.router.add_post("/api/spike/propozycja", spike_propozycja)


def _blad(status: int, kod: str, komunikat: str) -> web.Response:
    return web.json_response({"blad": kod, "komunikat": komunikat}, status=status)


def _user(request: web.Request) -> str:
    """Zwraca user.id po weryfikacji initData albo rzuca HTTPException."""
    try:
        user = auth.weryfikuj_init_data(request.headers.get("X-Init-Data", ""), token())
        return auth.sprawdz_usera(user)
    except auth.BladAuth as e:
        if str(e) == "uzytkownik":
            raise web.HTTPForbidden(text='{"blad":"uzytkownik"}', content_type="application/json")
        raise web.HTTPUnauthorized(text='{"blad":"podpis"}', content_type="application/json")


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "wersja": WERSJA})


# --- M0: diagnostyka integracji ----------------------------------------------

async def spike_kto(request: web.Request) -> web.Response:
    uid = _user(request)
    u = request.app["uslugi"]
    return web.json_response({"ok": True, "user": uid, "url": u.url, "gateway": gateway_most.diagnostyka()})


async def spike_haiku(request: web.Request) -> web.Response:
    _user(request)

    def wywolaj():
        from agent.auxiliary_client import call_llm
        r = call_llm(task="bibo_tryby", max_tokens=80, temperature=0, messages=[
            {"role": "system", "content": 'Odpowiedz wyłącznie JSON: {"ok": true, "slowo": str}'},
            {"role": "user", "content": "Jedno polskie słowo kojarzące się z detektywem."}])
        return r.choices[0].message.content, getattr(r, "model", None)

    try:
        tekst, model = await asyncio.get_running_loop().run_in_executor(None, wywolaj)
        return web.json_response({"ok": True, "odpowiedz": tekst, "model": model})
    except Exception as e:
        log.warning("bibo-tryby: haiku spike: %s", e)
        return _blad(503, "model", f"{type(e).__name__}: {e}"[:300])


async def spike_karta(request: web.Request) -> web.Response:
    uid = _user(request)
    u = request.app["uslugi"]
    try:
        await u.bot.karta(uid, str(ZASOBY / "radosc.png"),
                          "<b>📁 SPRAWA #0 · TEST</b>\n💥 WYMÓWKA OBALONA\n👣 <b>Test karty wyniku z efektem</b>",
                          efekt=EFEKT_KONFETTI)
        return web.json_response({"ok": True})
    except BladTelegrama as e:
        return _blad(502, "telegram", str(e))


async def spike_bibo(request: web.Request) -> web.Response:
    uid = _user(request)
    tekst = ("[bibo-tryby · notatka systemowa, nie wiadomość od usera]\n"
             "To test wtyczki Bibotektyw (M0). Odpowiedz userowi jednym krótkim zdaniem, "
             "że dostałeś notatkę z Mini App i wszystko działa.")
    sposob = await gateway_most.wstrzyknij(uid, tekst)
    return web.json_response({"ok": True, "sposob": sposob})


async def spike_propozycja(request: web.Request) -> web.Response:
    uid = _user(request)
    u = request.app["uslugi"]
    try:
        await u.bot.wiadomosc_z_aplikacja(uid, "🕵️ (test) Brzmi jak klasyczny zator. Otwieramy śledztwo?",
                                          "🔍 Otwieramy", u.url or "")
        return web.json_response({"ok": True})
    except BladTelegrama as e:
        return _blad(502, "telegram", str(e))


async def spike_strona(request: web.Request) -> web.Response:
    return web.Response(text=_STRONA.replace("{{WERSJA}}", html.escape(WERSJA)),
                        content_type="text/html", headers={"Cache-Control": "no-store"})


_STRONA = """<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Bibotektyw · M0</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
body{font:15px/1.45 system-ui,sans-serif;margin:0;padding:16px;background:#F2F2F2;color:#111}
h1{font-size:20px;margin:0 0 4px;color:#009688}p{margin:0 0 12px;color:#555}
button{display:block;width:100%;margin:8px 0;padding:12px;border:2px solid #000;border-radius:8px;
background:#fff;font:600 15px system-ui;text-align:left}
pre{white-space:pre-wrap;word-break:break-word;background:#fff;border:1px solid #ddd;border-radius:8px;
padding:10px;font-size:12px;min-height:60px}
</style></head><body>
<h1>Bibotektyw · diagnostyka M0</h1><p>Wersja wtyczki {{WERSJA}}. Klikaj po kolei i przepisz wyniki.</p>
<button data-t="kto">1. Podpis Telegrama i stan gatewaya</button>
<button data-t="haiku">2. Haiku przez logowanie Hermesa</button>
<button data-t="karta">3. Karta wyniku z konfetti (sprawdź czat)</button>
<button data-t="propozycja">4. Wiadomość z przyciskiem Mini App (sprawdź czat)</button>
<button data-t="bibo">5. Notatka do Bibo → Bibo odpisuje w czacie</button>
<button id="haptic">6. Wibracja (haptyka)</button>
<pre id="out">Telegram WebApp: …</pre>
<script>
const tg = window.Telegram && Telegram.WebApp; const out = document.getElementById('out');
function log(x){ out.textContent = typeof x === 'string' ? x : JSON.stringify(x, null, 2); }
if (tg) { tg.ready(); tg.expand();
  try { tg.setHeaderColor('#FFFFFF'); tg.setBackgroundColor('#F2F2F2'); } catch(e) {}
  log({wersja_webapp: tg.version, platforma: tg.platform, initData: tg.initData ? 'jest' : 'BRAK (otwórz z Telegrama)'}); }
else log('Brak Telegram.WebApp — otwórz stronę z bota.');
document.querySelectorAll('[data-t]').forEach(b => b.onclick = async () => {
  log('…');
  try { const r = await fetch('/api/spike/' + b.dataset.t, {method:'POST',
          headers: {'X-Init-Data': tg ? tg.initData : ''}});
        log({status: r.status, ...(await r.json().catch(() => ({})))}); }
  catch (e) { log(String(e)); } });
document.getElementById('haptic').onclick = () => {
  try { tg.HapticFeedback.notificationOccurred('success'); log('haptyka: wysłana'); } catch(e) { log(String(e)); } };
</script></body></html>"""
