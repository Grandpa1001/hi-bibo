"""Testy pętli kontroli terminów."""
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402

kontrola = podmodul("bibo-tryby", "kontrola")
magazyn = podmodul("bibo-tryby", "magazyn")


def uslugi_atrapa(url: str = "https://abc.trycloudflare.com"):
    u = MagicMock()
    u.url = url
    u.bot = MagicMock()
    u.bot.wiadomosc_z_aplikacja = AsyncMock(return_value={"message_id": 1})
    return u


class Sprawdz(unittest.IsolatedAsyncioTestCase):
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

    def _zapisz_sprawe(self, sid, **pola):
        stan = magazyn.sprawy()
        baza = {"numer": 1, "user": "42", "etap": "zamknieta",
                "ostatnia_akcja": magazyn.iso(), "kontrola": None,
                "kontrola_wyslana": False, "krok": "otwórz repo"}
        stan[sid] = {**baza, **pola}
        magazyn.zapisz_sprawy(stan)

    async def test_wysyla_po_terminie(self):
        u = uslugi_atrapa()
        self._zapisz_sprawe("s_a", kontrola=magazyn.iso(magazyn.teraz() - timedelta(minutes=1)))
        self.assertEqual(await kontrola.sprawdz(u), 1)
        u.bot.wiadomosc_z_aplikacja.assert_awaited_once()
        stan = magazyn.sprawy()
        self.assertTrue(stan["s_a"]["kontrola_wyslana"])

    async def test_nie_wysyla_ponownie(self):
        u = uslugi_atrapa()
        self._zapisz_sprawe("s_a", kontrola=magazyn.iso(magazyn.teraz() - timedelta(minutes=1)))
        await kontrola.sprawdz(u)
        await kontrola.sprawdz(u)
        u.bot.wiadomosc_z_aplikacja.assert_awaited_once()

    async def test_pomija_przyszly_termin(self):
        u = uslugi_atrapa()
        self._zapisz_sprawe("s_a", kontrola=magazyn.iso(magazyn.teraz() + timedelta(minutes=5)))
        self.assertEqual(await kontrola.sprawdz(u), 0)
        u.bot.wiadomosc_z_aplikacja.assert_not_awaited()

    async def test_pomija_niezamknieta_lub_bez_terminu(self):
        u = uslugi_atrapa()
        self._zapisz_sprawe("s_a", etap="zeznanie",
                            kontrola=magazyn.iso(magazyn.teraz() - timedelta(minutes=1)))
        self._zapisz_sprawe("s_b", kontrola=None)
        self.assertEqual(await kontrola.sprawdz(u), 0)
        u.bot.wiadomosc_z_aplikacja.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
