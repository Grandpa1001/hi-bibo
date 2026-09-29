"""python -m unittest discover -s tests/bibo_tryby  (z katalogu repo, w środowisku Hermesa)."""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402

api = podmodul("bibo-tryby", "api")
auth = podmodul("bibo-tryby", "auth")
magazyn = podmodul("bibo-tryby", "magazyn")
detektyw = podmodul("bibo-tryby", "tryby.detektyw")

TOKEN = "123456:TEST-token"
UID = 42


def podpisz(user_id: int = UID, teraz: int | None = None, token: str = TOKEN) -> str:
    pola = {"auth_date": str(int(teraz if teraz is not None else time.time())),
            "query_id": "AAE", "signature": "abc",
            "user": json.dumps({"id": user_id, "first_name": "Kamil"}, separators=(",", ":"))}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(pola.items()))
    sekret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return urlencode({**pola, "hash": hmac.new(sekret, dcs.encode(), hashlib.sha256).hexdigest()})


ZEZNANIE_OK = {"podejrzany": "Perfekcjonista", "emoji": "🎩", "nowy": False,
               "pytanie": "Jaka wersja na 60% przydałaby się już dziś?",
               "podpowiedz": "Szkielet nie blokuje animacji."}
WERDYKT_OK = {"werdykt": "obalona",
              "podsumowanie": "Perfekcjonista udawał, że bez GSAP nie ma strony.",
              "krok": "Otwórz repo i utwórz pusty index.html"}


class BazaApi(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._stare = {k: os.environ.get(k) for k in
                       ("HERMES_HOME", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS")}
        os.environ["HERMES_HOME"] = self.tmp.name
        os.environ["TELEGRAM_BOT_TOKEN"] = TOKEN
        os.environ["TELEGRAM_ALLOWED_USERS"] = str(UID)

        self.odpowiedzi = []
        self.wiadomosci = []

        def wywolaj(messages, temperature, max_tokens):
            self.wiadomosci.append(messages)
            o = self.odpowiedzi.pop(0)
            if isinstance(o, Exception):
                raise o
            return o if isinstance(o, str) else json.dumps(o, ensure_ascii=False)

        app = web.Application(client_max_size=4096, middlewares=[api.bledy])
        app["wywolaj_haiku"] = wywolaj
        api.trasy(app)
        self.server = TestServer(app)
        await self.server.start_server()
        self.client = TestClient(self.server)
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.server.close()
        for k, v in self._stare.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def naglowki(self, user_id: int = UID) -> dict:
        return {"X-Init-Data": podpisz(user_id)}

    async def POST(self, sciezka, dane=None, naglowki=None):
        return await self.client.post(sciezka, json=(dane if dane is not None else {}),
                                      headers=naglowki if naglowki is not None else self.naglowki())

    async def GET(self, sciezka, naglowki=None):
        return await self.client.get(sciezka, headers=naglowki if naglowki is not None else self.naglowki())


class PelnaSprawa(BazaApi):
    async def test_happy_path(self):
        self.odpowiedzi = [ZEZNANIE_OK, WERDYKT_OK]

        r = await self.POST("/api/sprawa")
        self.assertEqual(r.status, 201)
        sprawa = await r.json()
        self.assertEqual(sprawa["numer"], 1)
        sid = sprawa["id"]

        r = await self.POST(f"/api/sprawa/{sid}/zeznanie",
                            {"wymowka": "Muszę najpierw idealny research, potem kodu tknę."})
        self.assertEqual(r.status, 200)
        z = await r.json()
        self.assertEqual((z["podejrzany"]["nazwa"], z["podejrzany"]["emoji"], z["zrodlo"]),
                         ("Perfekcjonista", "🎩", "model"))
        self.assertEqual(z["podejrzany"]["zatrzymanie"], 1)

        r = await self.POST(f"/api/sprawa/{sid}/riposta",
                            {"riposta": "Mogę postawić szkielet, animacje później."})
        w = await r.json()
        self.assertEqual((r.status, w["werdykt"], w["zrodlo"]),
                         (200, "obalona", "model"))

        r = await self.POST(f"/api/sprawa/{sid}/zamknij", {"kontrola_min": 10})
        z = await r.json()
        self.assertEqual(r.status, 200)
        self.assertIsNotNone(z["kontrola"])

        r = await self.GET("/api/hub")
        h = await r.json()
        self.assertEqual(h["statystyki"], {"zamkniete": 1, "obalone": 1,
                                           "najczestszy": {"nazwa": "Perfekcjonista", "emoji": "🎩"}})
        self.assertIsNone(h["aktywna_sprawa"])   # zamknięta po zamknij

        r = await self.GET("/api/kartoteka")
        k = await r.json()
        self.assertEqual(len(k["sprawy"]), 1)
        perf = next(p for p in k["podejrzani"] if p["nazwa"] == "Perfekcjonista")
        self.assertEqual((perf["zatrzymania"], perf["obalone"]), (1, 1))

        kart = magazyn.kartoteka()
        self.assertIn("Sprawa #1", kart["notatka_dla_bibo"])
        self.assertIn("Perfekcjonista", kart["notatka_dla_bibo"])

    async def test_uniewinnienie_bez_riposty(self):
        self.odpowiedzi = [{**ZEZNANIE_OK, "podejrzany": "Brak Paliwa", "emoji": "🔋"},
                           {"werdykt": "uniewinniona",
                            "podsumowanie": "Prawdziwe zmęczenie — nie robimy więcej dziś.",
                            "krok": "Zrób sobie 10 minut przerwy bez telefonu"}]
        r = await self.POST("/api/sprawa")
        sid = (await r.json())["id"]
        await self.POST(f"/api/sprawa/{sid}/zeznanie",
                        {"wymowka": "Ledwo stoję po nocce, nic nie zrobię."})
        r = await self.POST(f"/api/sprawa/{sid}/riposta", {"uniewinnienie": True})
        w = await r.json()
        self.assertEqual(w["werdykt"], "uniewinniona")
        self.assertIn("<tryb>uniewinnienie</tryb>", self.wiadomosci[1][1]["content"])

    async def test_kontrola_ruszylo(self):
        self.odpowiedzi = [ZEZNANIE_OK, WERDYKT_OK]
        r = await self.POST("/api/sprawa")
        sid = (await r.json())["id"]
        await self.POST(f"/api/sprawa/{sid}/zeznanie", {"wymowka": "Muszę idealnie."})
        await self.POST(f"/api/sprawa/{sid}/riposta", {"riposta": "Ok, wersja 60%."})
        await self.POST(f"/api/sprawa/{sid}/zamknij", {"kontrola_min": 10})

        r = await self.POST(f"/api/sprawa/{sid}/kontrola", {"ruszylo": True})
        self.assertEqual(r.status, 200)
        perf = next(p for p in (await (await self.GET("/api/kartoteka")).json())["podejrzani"]
                    if p["nazwa"] == "Perfekcjonista")
        self.assertEqual(perf["ruszylo"], 1)
        # po odbytej kontroli sprawa znika z aktywnych — 404 przy powtórnej próbie
        r = await self.POST(f"/api/sprawa/{sid}/kontrola", {"ruszylo": False})
        self.assertEqual(r.status, 404)

    async def test_druga_sprawa_porzuca_pierwsza(self):
        r1 = (await (await self.POST("/api/sprawa")).json())["id"]
        r2 = (await (await self.POST("/api/sprawa")).json())["id"]
        self.assertNotEqual(r1, r2)
        self.odpowiedzi = [ZEZNANIE_OK]
        r = await self.POST(f"/api/sprawa/{r1}/zeznanie", {"wymowka": "cokolwiek"})
        self.assertEqual(r.status, 404)   # porzucona


class KodyBledow(BazaApi):
    async def test_401_bez_initdata(self):
        for r in (await self.client.get("/api/hub"),
                  await self.client.get("/api/hub", headers={"X-Init-Data": "smieci"})):
            j = await r.json()
            self.assertEqual((r.status, j["blad"]), (401, "podpis"))
            self.assertTrue(j["komunikat"])

    async def test_403_obcy_user(self):
        r = await self.GET("/api/hub", naglowki={"X-Init-Data": podpisz(user_id=999)})
        j = await r.json()
        self.assertEqual((r.status, j["blad"]), (403, "uzytkownik"))

    async def test_404_nieznana_sprawa(self):
        r = await self.POST("/api/sprawa/s_ffff/zeznanie", {"wymowka": "x"})
        j = await r.json()
        self.assertEqual((r.status, j["blad"]), (404, "sprawa"))

    async def test_409_riposta_bez_zeznania(self):
        sid = (await (await self.POST("/api/sprawa")).json())["id"]
        r = await self.POST(f"/api/sprawa/{sid}/riposta", {"riposta": "x"})
        j = await r.json()
        self.assertEqual((r.status, j["blad"]), (409, "stan"))

    async def test_409_zamknij_bez_werdyktu(self):
        self.odpowiedzi = [ZEZNANIE_OK]
        sid = (await (await self.POST("/api/sprawa")).json())["id"]
        await self.POST(f"/api/sprawa/{sid}/zeznanie", {"wymowka": "abc"})
        r = await self.POST(f"/api/sprawa/{sid}/zamknij", {"kontrola_min": 10})
        j = await r.json()
        self.assertEqual((r.status, j["blad"]), (409, "stan"))

    async def test_422_pusta_wymowka(self):
        sid = (await (await self.POST("/api/sprawa")).json())["id"]
        for tresc in ({}, {"wymowka": ""}, {"wymowka": "   "}, {"wymowka": "x" * 600}):
            r = await self.POST(f"/api/sprawa/{sid}/zeznanie", tresc)
            j = await r.json()
            self.assertEqual((r.status, j["blad"]), (422, "dane"))

    async def test_422_riposta_bez_niczego(self):
        self.odpowiedzi = [ZEZNANIE_OK]
        sid = (await (await self.POST("/api/sprawa")).json())["id"]
        await self.POST(f"/api/sprawa/{sid}/zeznanie", {"wymowka": "abc"})
        r = await self.POST(f"/api/sprawa/{sid}/riposta", {})
        j = await r.json()
        self.assertEqual((r.status, j["blad"]), (422, "dane"))

    async def test_422_zla_wartosc_kontrola(self):
        self.odpowiedzi = [ZEZNANIE_OK, WERDYKT_OK]
        sid = (await (await self.POST("/api/sprawa")).json())["id"]
        await self.POST(f"/api/sprawa/{sid}/zeznanie", {"wymowka": "abc"})
        await self.POST(f"/api/sprawa/{sid}/riposta", {"riposta": "ok"})
        r = await self.POST(f"/api/sprawa/{sid}/zamknij", {"kontrola_min": -5})
        j = await r.json()
        self.assertEqual((r.status, j["blad"]), (422, "dane"))

    async def test_429_limit_haiku(self):
        magazyn.zapisz("ustawienia.json", {"limit_haiku_na_godzine": 1})
        self.odpowiedzi = [ZEZNANIE_OK]
        sid1 = (await (await self.POST("/api/sprawa")).json())["id"]
        r = await self.POST(f"/api/sprawa/{sid1}/zeznanie", {"wymowka": "abc"})
        self.assertEqual(r.status, 200)
        # druga próba w tej samej godzinie → 429
        sid2 = (await (await self.POST("/api/sprawa")).json())["id"]
        r = await self.POST(f"/api/sprawa/{sid2}/zeznanie", {"wymowka": "abc"})
        j = await r.json()
        self.assertEqual((r.status, j["blad"]), (429, "limit"))

    async def test_503_awaria_modelu_bez_zapisu_i_bez_werdyktu(self):
        self.odpowiedzi = ["nie json", "{}"]
        sid = (await (await self.POST("/api/sprawa")).json())["id"]
        r = await self.POST(f"/api/sprawa/{sid}/zeznanie", {"wymowka": "Zrobię to jutro."})
        j = await r.json()
        self.assertEqual((r.status, j["blad"]), (503, "model"))
        self.assertNotIn("werdykt", j)
        self.assertEqual(magazyn.kartoteka()["podejrzani"]["Jutrzejszy Ja"]["zatrzymania"], 0)
        self.assertEqual(magazyn.sprawy()[sid]["etap"], "nowa")   # można ponowić

    async def test_health_bez_auth(self):
        r = await self.client.get("/health")
        j = await r.json()
        self.assertEqual((r.status, j["ok"]), (200, True))
        self.assertNotIn("adres", j)

    async def test_body_za_duze(self):
        sid = (await (await self.POST("/api/sprawa")).json())["id"]
        r = await self.POST(f"/api/sprawa/{sid}/zeznanie", {"wymowka": "x" * 8000})
        # aiohttp: 413 → mieszamy w 422 (nasz kontrakt); status = 422 lub 413
        self.assertIn(r.status, (413, 422))
        if r.status == 422:
            self.assertEqual((await r.json())["blad"], "dane")


if __name__ == "__main__":
    unittest.main()
