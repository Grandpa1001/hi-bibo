"""API widgetu stanu dnia: odczyt dnia i tygodnia, wpis z Mini App, doprecyzowanie, uwaga, uprawnienia."""
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402
from test_api import BazaApi, UID  # noqa: E402

stan = podmodul("bibo-tryby", "stan")
siatka = podmodul("bibo-tryby", "siatka")


class Widget(BazaApi):
    async def test_pusty_dzien_i_siedem_dni(self):
        r = await self.GET("/api/stan")
        d = await r.json()
        self.assertEqual((r.status, d["wlaczone"], d["dzis"]), (200, True, None))
        self.assertEqual(len(d["tydzien"]), 7)
        self.assertTrue(all(x["cwiartka"] is None for x in d["tydzien"]))

    async def test_wpis_z_siatki_daje_tryb_reakcje_i_zrodlo_widget(self):
        r = await self.POST("/api/stan", {"energia": 2, "przyjemnosc": -1})
        d = await r.json()
        self.assertEqual(r.status, 200)
        self.assertEqual((d["dzis"]["cwiartka"], d["dzis"]["nazwa"], d["dzis"]["uwaga"]), ("tension", "Napięcie", "normal"))
        self.assertEqual(len(d["reakcja"].split("\n")), 2)
        self.assertEqual(d["tydzien"][-1]["cwiartka"], "tension")
        self.assertEqual(d["dzis"]["slowa"], list(stan.SLOWA["tension"]))
        w = stan.dzisiejszy(str(UID))
        self.assertEqual(w["zrodlo"], "widget")

    async def test_wpis_z_uwaga_od_razu(self):
        d = await (await self.POST("/api/stan", {"energia": -2, "przyjemnosc": 2, "uwaga": "hyperfocus"})).json()
        self.assertEqual((d["dzis"]["cwiartka"], d["dzis"]["uwaga"]), ("steady", "hyperfocus"))

    async def test_slowo_notatka_i_uwaga(self):
        await self.POST("/api/stan", {"energia": 2, "przyjemnosc": 2})
        r = await self.POST("/api/stan/doprecyzuj", {"slowo": "skupiony", "notatka": "dobry start"})
        self.assertEqual((await r.json())["dzis"]["slowo"], "skupiony")
        r = await self.POST("/api/stan/uwaga", {"uwaga": "hyperfocus"})
        d = await r.json()
        self.assertEqual((d["dzis"]["uwaga"], d["dzis"]["cwiartka"], d["dzis"]["slowo"]), ("hyperfocus", "peak", "skupiony"))
        self.assertIn("hiperfokus", d["komunikat"])
        r = await self.POST("/api/stan/uwaga", {"uwaga": "normal"})
        self.assertIn("Witaj z powrotem", (await r.json())["komunikat"])

    async def test_bledy_danych_i_brak_wpisu(self):
        for dane in ({"energia": 9, "przyjemnosc": 0}, {"energia": "x", "przyjemnosc": 0}, {}, {"energia": 1, "przyjemnosc": 1, "uwaga": "x"}):
            r = await self.POST("/api/stan", dane)
            self.assertEqual((r.status, (await r.json())["blad"]), (422, "dane"), dane)
        self.assertIsNone(stan.dzisiejszy(str(UID)))
        for sciezka, dane in (("/api/stan/uwaga", {"uwaga": "hyperfocus"}), ("/api/stan/doprecyzuj", {"slowo": "skupiony"})):
            r = await self.POST(sciezka, dane)
            self.assertEqual((r.status, (await r.json())["blad"]), (409, "brak_wpisu"), sciezka)

    async def test_slowo_spoza_cwiartki(self):
        await self.POST("/api/stan", {"energia": 2, "przyjemnosc": 2})
        r = await self.POST("/api/stan/doprecyzuj", {"slowo": "wyczerpany"})
        self.assertEqual(r.status, 422)

    async def test_uprawnienia(self):
        self.assertEqual((await self.GET("/api/stan", naglowki={})).status, 401)
        self.assertEqual((await self.POST("/api/stan", {"energia": 1, "przyjemnosc": 1}, naglowki={})).status, 401)
        os.environ["TELEGRAM_ALLOWED_USERS"] = f"{UID},7"      # dwóch userów: brak jednego właściciela
        r = await self.POST("/api/stan", {"energia": 1, "przyjemnosc": 1})
        self.assertEqual(r.status, 403)
        self.assertEqual(await (await self.GET("/api/stan")).json(), {"wlaczone": False})

    async def test_wylaczone_w_ustawieniach(self):
        with mock.patch.object(siatka.magazyn, "ustawienia", return_value={"stan": False}):
            self.assertEqual(await (await self.GET("/api/stan")).json(), {"wlaczone": False})
            r = await self.POST("/api/stan", {"energia": 1, "przyjemnosc": 1})
            self.assertEqual((r.status, (await r.json())["blad"]), (409, "wylaczone"))
        self.assertIsNone(stan.dzisiejszy(str(UID)))


if __name__ == "__main__":
    unittest.main()
