"""Testy wysyłania do czatu Telegrama (propozycja, karta, kontrola, notatka)."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402

czat = podmodul("bibo-tryby", "czat")
magazyn = podmodul("bibo-tryby", "magazyn")


def uslugi_atrapa(url: str = "https://abc.trycloudflare.com") -> MagicMock:
    u = MagicMock()
    u.url = url
    u.bot = MagicMock()
    u.bot.wiadomosc_z_aplikacja = AsyncMock(return_value={"message_id": 1})
    u.bot.karta = AsyncMock(return_value={"message_id": 2})
    return u


class Propozycja(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._stare = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name

    def tearDown(self):
        if self._stare is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._stare
        self.tmp.cleanup()

    async def test_wysyla_i_zwieksza_licznik(self):
        u = uslugi_atrapa()
        wynik = await czat.wyslij_propozycje("42", u)
        self.assertTrue(wynik)
        u.bot.wiadomosc_z_aplikacja.assert_awaited_once()
        args, kwargs = u.bot.wiadomosc_z_aplikacja.await_args
        self.assertEqual(args[0], "42")           # uid
        self.assertEqual(args[3], u.url)          # url
        kart = magazyn.kartoteka()
        self.assertEqual(kart["propozycje"][magazyn.data()], 1)

    async def test_drugi_raz_tego_samego_dnia_nie_wysyla(self):
        u = uslugi_atrapa()
        self.assertTrue(await czat.wyslij_propozycje("42", u))
        self.assertFalse(await czat.wyslij_propozycje("42", u))
        u.bot.wiadomosc_z_aplikacja.assert_awaited_once()

    async def test_limit_zero_blokuje(self):
        magazyn.zapisz("ustawienia.json", {"propozycje_dziennie": 0})
        u = uslugi_atrapa()
        self.assertFalse(await czat.wyslij_propozycje("42", u))
        u.bot.wiadomosc_z_aplikacja.assert_not_awaited()

    async def test_bez_url_nie_wysyla(self):
        u = uslugi_atrapa(url=None)
        self.assertFalse(await czat.wyslij_propozycje("42", u))
        u.bot.wiadomosc_z_aplikacja.assert_not_awaited()


class Karta(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._stare = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name

    def tearDown(self):
        if self._stare is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._stare
        self.tmp.cleanup()

    async def test_podpis_i_efekt(self):
        u = uslugi_atrapa()
        sprawa = {"numer": 7, "werdykt": "obalona", "krok": "Otwórz repo i utwórz pusty index.html"}
        self.assertTrue(await czat.wyslij_karte("42", sprawa, u))
        args, kwargs = u.bot.karta.await_args
        podpis = args[2]
        self.assertIn("SPRAWA #07", podpis)
        self.assertIn("OBALONA", podpis)
        self.assertIn("Otwórz repo", podpis)
        self.assertEqual(kwargs.get("efekt"), czat.EFEKT_KONFETTI)

    async def test_awaryjny_plik_gdy_brak_static(self):
        u = uslugi_atrapa()
        await czat.wyslij_karte("42", {"numer": 1, "werdykt": "czesciowo", "krok": "x"}, u)
        args, _ = u.bot.karta.await_args
        self.assertTrue(args[1].endswith(".png"))


class Kontrola(unittest.IsolatedAsyncioTestCase):
    async def test_url_z_hashem_kontrola(self):
        u = uslugi_atrapa()
        sprawa = {"numer": 3, "krok": "otwórz repo"}
        self.assertTrue(await czat.wyslij_kontrole("42", "s_abcd", sprawa, u))
        args, _ = u.bot.wiadomosc_z_aplikacja.await_args
        self.assertIn("Kontrola po sprawie #03", args[1])
        self.assertEqual(args[3], f"{u.url}/#/kontrola/s_abcd")

    async def test_bez_url_brak_wysylki(self):
        u = uslugi_atrapa(url=None)
        self.assertFalse(await czat.wyslij_kontrole("42", "s_x", {"numer": 1, "krok": "x"}, u))


class KomentarzBibo(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._stare = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name

    def tearDown(self):
        if self._stare is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._stare
        self.tmp.cleanup()

    async def test_fallback_bo_brak_runnera(self):
        # gateway_most.wstrzyknij bez runnera → "notatka" (do notatki.json), a nie sesja
        magazyn.zapisz_kartoteke({**magazyn._pusta_kartoteka(), "notatka_dla_bibo": "hej"})
        sposob = await czat.powiadom_bibo("42", "hej")
        self.assertEqual(sposob, "notatka")
        self.assertIsNone(magazyn.kartoteka()["notatka_dla_bibo"])   # wyczyszczone

    async def test_zapytaj_co_blokuje(self):
        sposob = await czat.zapytaj_co_blokuje("42", {"numer": 7, "krok": "otwórz repo"})
        self.assertEqual(sposob, "notatka")
        notatka = "\n\n".join(magazyn.czytaj("notatki.json", []) or [])
        self.assertIn("Kontrola sprawy #7", notatka)
        self.assertIn("otwórz repo", notatka)


if __name__ == "__main__":
    unittest.main()
