"""Tryb dnia i reakcja (FR-3/FR-4), aktywność w tle (FR-10) i podpięcie do tury modelu."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul, wtyczka  # noqa: E402

stan = podmodul("bibo-tryby", "stan")
tryb = podmodul("bibo-tryby", "tryb")
karta = podmodul("bibo-tryby", "karta")
kontakt = podmodul("bibo-tryby", "kontakt")
siatka = podmodul("bibo-tryby", "siatka")
wt = wtyczka("bibo-tryby")

W = "42"
TERAZ = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)   # 14:00 w Warszawie


class Baza(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "s.sqlite3"
        self.kdb = Path(self.tmp.name) / "k.sqlite3"
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": W, "HERMES_HOME": self.tmp.name})
        self.env.start()
        os.environ.pop("BIBO_STREFA", None)
        self.zegar = mock.patch.object(kontakt, "teraz", return_value=TERAZ)
        self.zegar.start()

    def tearDown(self):
        self.zegar.stop()
        self.env.stop()
        self.tmp.cleanup()


class Tryby(Baza):
    def test_kazda_cwiartka_ma_inne_wytyczne_i_reakcje(self):
        wyt = {tryb.WYTYCZNE[c] for c in stan.CWIARTKI}
        rea = {tryb.reakcja(c) for c in stan.CWIARTKI}
        self.assertEqual((len(wyt), len(rea)), (4, 4))

    def test_reakcja_to_jedno_zdanie_i_jeden_krok(self):
        for c in stan.CWIARTKI:
            linie = tryb.reakcja(c, "Wypisz trzy punkty").split("\n")
            self.assertEqual(len(linie), 2, c)
            self.assertTrue(linie[1].startswith("👣"))
            self.assertEqual(linie[0].count("."), 1, c)

    def test_krok_z_karty_ma_pierwszenstwo_ale_nie_w_regeneracji(self):
        self.assertIn("Wypisz trzy punkty", tryb.reakcja("tension", "Wypisz trzy punkty"))
        self.assertNotIn("Wypisz", tryb.reakcja("recovery", "Wypisz trzy punkty"))
        self.assertIn("…", tryb.reakcja("peak", "x" * 200))

    def test_kontekst_tylko_gdy_jest_wpis(self):
        self.assertIsNone(tryb.kontekst(None))
        k = tryb.kontekst({"cwiartka": "tension"})
        self.assertIn("Napięcie", k)
        self.assertIn("2–3 zadania", k)
        self.assertLess(len(k), 400)   # stały, mały koszt na turę

    def test_tap_w_rozmowie_daje_reakcje_z_krokiem_karty(self):
        karta.utworz(W, {"cel": "Raport", "krok": "Wypisz trzy punkty"})
        odp = siatka.obsluz(W, "⚡⚡ 😣", teraz=TERAZ, sciezka=self.db)   # napięcie
        self.assertIn("Zapisane: Napięcie.", odp["text"])
        self.assertIn("Wypisz trzy punkty", odp["text"])
        self.assertIn("opcjonalne", odp["text"])


class Aktywnosc(Baza):
    def tura(self, dt):
        return stan.rejestruj_ture(W, teraz=dt, sciezka=self.db)

    def test_sesje_i_czas_z_przerwa_30_min(self):
        self.tura(TERAZ)
        self.tura(TERAZ + timedelta(minutes=10))
        self.tura(TERAZ + timedelta(minutes=25))                 # ta sama sesja: 25 min
        self.tura(TERAZ + timedelta(minutes=25 + 31))            # nowa sesja
        z = stan.zaangazowanie(W, teraz=TERAZ + timedelta(hours=1), sciezka=self.db, sciezka_karty=self.kdb)
        self.assertEqual((z["tury"], z["sesje"], z["minuty"], z["domkniecia"]), (4, 2, 25, 0))

    def test_zwraca_tryb_dnia_w_tej_samej_transakcji(self):
        self.assertIsNone(self.tura(TERAZ))
        stan.zapisz_wpis(W, -2, -2, teraz=TERAZ, sciezka=self.db)
        self.assertEqual(self.tura(TERAZ + timedelta(minutes=1))["cwiartka"], "recovery")

    def test_domkniecia_to_zakonczone_dzis_karty(self):
        karta.utworz(W, {"cel": "A"}, sciezka=self.kdb)
        with mock.patch.object(karta, "_teraz", return_value=kontakt.teraz().astimezone(kontakt.strefa()).isoformat(timespec="seconds")):
            karta.przenies(W, "zakonczona", sciezka=self.kdb)
        z = stan.zaangazowanie(W, teraz=TERAZ, sciezka=self.db, sciezka_karty=self.kdb)
        self.assertEqual(z["domkniecia"], 1)
        z = stan.zaangazowanie(W, teraz=TERAZ + timedelta(days=1), sciezka=self.db, sciezka_karty=self.kdb)
        self.assertEqual(z["domkniecia"], 0)

    def test_stare_dni_sa_czyszczone(self):
        self.tura(TERAZ - timedelta(days=70))
        self.tura(TERAZ)
        with stan._polacz(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM aktywnosc").fetchone()[0], 1)


class WTurze(Baza):
    def test_kontekst_tury_zalezy_od_trybu_i_tylko_dla_wlasciciela(self):
        self.assertIsNone(wt._tryb_dnia("7"))                           # obcy user
        self.assertIsNone(wt._tryb_dnia(W))                             # brak wpisu
        stan.zapisz_wpis(W, 1, -1)                                      # napięcie (domyślna baza)
        self.assertIn("Napięcie", wt._tryb_dnia(W))
        stan.zapisz_wpis(W, -1, -1)
        self.assertIn("Regeneracja", wt._tryb_dnia(W))

    def test_przed_tura_dokleja_tryb_i_nie_psuje_sie_przy_awarii(self):
        stan.zapisz_wpis(W, 2, 2)
        r = wt._przed_tura(platform="telegram", sender_id=W)
        self.assertIn("Szczyt", r["context"])
        self.assertIsNone(wt._przed_tura(platform="cli", sender_id=W))
        with mock.patch.object(stan, "rejestruj_ture", side_effect=RuntimeError("dysk")):
            self.assertIsNone(wt._tryb_dnia(W))

    def test_wylaczone_nie_liczy_tur(self):
        with mock.patch.object(siatka.magazyn, "ustawienia", return_value={"stan": False}):
            self.assertIsNone(wt._tryb_dnia(W))
        self.assertEqual(stan.zaangazowanie(W)["tury"], 0)


if __name__ == "__main__":
    unittest.main()
