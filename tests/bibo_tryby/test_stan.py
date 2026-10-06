"""Stan dnia: ćwiartki z osi, doba usera, uwaga, tydzień, sygnały (kontrolowany zegar, osobna baza)."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402

stan = podmodul("bibo-tryby", "stan")
kontakt = podmodul("bibo-tryby", "kontakt")

W = "42"
# 14:00 w Warszawie (CEST)
TERAZ = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class Baza(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "s.sqlite3"
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": W, "HERMES_HOME": self.tmp.name})
        self.env.start()
        os.environ.pop("BIBO_STREFA", None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def wpis(self, e, p, teraz=TERAZ, **kw):
        return stan.zapisz_wpis(W, e, p, teraz=teraz, sciezka=self.db, **kw)


class Cwiartki(Baza):
    def test_cztery_cwiartki_i_zero_w_spokojna_strone(self):
        self.assertEqual(stan.cwiartka(2, 2), "peak")
        self.assertEqual(stan.cwiartka(-2, 1), "steady")
        self.assertEqual(stan.cwiartka(1, -1), "tension")
        self.assertEqual(stan.cwiartka(-1, -2), "recovery")
        self.assertEqual(stan.cwiartka(0, 0), "steady")      # środek siatki
        self.assertEqual(stan.cwiartka(0, 2), "steady")      # energia 0 = niska
        self.assertEqual(stan.cwiartka(2, 0), "peak")        # przyjemność 0 = przyjemnie

    def test_wpis_ma_cwiartke_z_osi_i_domyslna_uwage(self):
        r = self.wpis(2, -1)
        self.assertEqual((r["cwiartka"], r["uwaga"], r["zrodlo"], r["slowo"], r["notatka"]),
                         ("tension", "normal", "manual", None, None))

    def test_walidacja(self):
        for e, p in ((3, 0), (0, -3), (True, 0), ("1", 0), (1.0, 0), (None, 0)):
            with self.assertRaises(stan.BladStanu, msg=(e, p)):
                self.wpis(e, p)
        with self.assertRaises(stan.BladStanu):
            self.wpis(1, 1, uwaga="x")
        with self.assertRaises(stan.BladStanu):
            self.wpis(1, 1, zrodlo="x")

    def test_bez_wlasciciela_nic_sie_nie_zapisuje(self):
        with self.assertRaises(stan.BladStanu) as e:
            stan.zapisz_wpis(None, 1, 1, sciezka=self.db)
        self.assertEqual(e.exception.kod, "brak_wlasciciela")
        self.assertFalse(self.db.exists())


class Dzien(Baza):
    def test_tryb_to_ostatni_wpis_dnia(self):
        self.wpis(2, 2, TERAZ)
        self.wpis(-2, -2, TERAZ + timedelta(hours=2))
        self.assertEqual(stan.dzisiejszy(W, teraz=TERAZ + timedelta(hours=3), sciezka=self.db)["cwiartka"], "recovery")

    def test_doba_liczona_w_strefie_usera(self):
        # 22:30 UTC = 00:30 następnego dnia w Warszawie: wpis z poprzedniego dnia lokalnego nie jest „dzisiejszy”
        wczoraj = datetime(2026, 10, 1, 21, 30, tzinfo=timezone.utc)   # 23:30 lokalnie, 1 października
        self.wpis(2, 2, wczoraj)
        po_polnocy = datetime(2026, 10, 1, 22, 30, tzinfo=timezone.utc)   # 00:30 lokalnie, 2 października
        self.assertIsNone(stan.dzisiejszy(W, teraz=po_polnocy, sciezka=self.db))
        self.assertIsNotNone(stan.dzisiejszy(W, teraz=wczoraj + timedelta(minutes=10), sciezka=self.db))

    def test_inny_wlasciciel_nie_widzi_wpisow(self):
        self.wpis(2, 2)
        with mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "7"}):
            self.assertIsNone(stan.dzisiejszy("7", teraz=TERAZ, sciezka=self.db))


class Doprecyzowanie(Baza):
    def test_slowo_i_notatka_do_ostatniego_wpisu(self):
        self.wpis(2, 2)
        r = stan.doprecyzuj(W, slowo="skupiony", notatka="  dużo\n  planów <b> ", teraz=TERAZ, sciezka=self.db)
        self.assertEqual((r["slowo"], r["notatka"]), ("skupiony", "dużo planów ‹b›"))

    def test_slowo_spoza_cwiartki_odrzucone_i_nic_nie_zmienia(self):
        self.wpis(2, 2)
        with self.assertRaises(stan.BladStanu):
            stan.doprecyzuj(W, slowo="wyczerpany", teraz=TERAZ, sciezka=self.db)
        self.assertIsNone(stan.dzisiejszy(W, teraz=TERAZ, sciezka=self.db)["slowo"])

    def test_pominiecie_i_brak_wpisu(self):
        self.wpis(2, 2)
        r = stan.doprecyzuj(W, teraz=TERAZ, sciezka=self.db)   # oba opcjonalne
        self.assertEqual((r["slowo"], r["notatka"]), (None, None))
        with self.assertRaises(stan.BladStanu) as e:
            stan.doprecyzuj(W, teraz=TERAZ + timedelta(days=1), sciezka=self.db)
        self.assertEqual(e.exception.kod, "brak_wpisu")

    def test_za_dluga_notatka(self):
        self.wpis(2, 2)
        with self.assertRaises(stan.BladStanu):
            stan.doprecyzuj(W, notatka="x" * 301, teraz=TERAZ, sciezka=self.db)


class Uwaga(Baza):
    def test_zmiana_uwagi_to_nowy_wpis_z_tymi_samymi_osiami(self):
        a = self.wpis(-2, -2)
        b = stan.ustaw_uwage(W, "hyperfocus", teraz=TERAZ + timedelta(hours=1), sciezka=self.db)
        self.assertNotEqual(a["id"], b["id"])
        self.assertEqual((b["cwiartka"], b["energia"], b["przyjemnosc"], b["uwaga"]), ("recovery", -2, -2, "hyperfocus"))
        d = stan.dzisiejszy(W, teraz=TERAZ + timedelta(hours=2), sciezka=self.db)
        self.assertEqual((d["cwiartka"], d["uwaga"]), ("recovery", "hyperfocus"))

    def test_zmiana_uwagi_zachowuje_slowo_i_notatke(self):
        self.wpis(2, 2)
        stan.doprecyzuj(W, slowo="skupiony", notatka="dobry start", teraz=TERAZ, sciezka=self.db)
        b = stan.ustaw_uwage(W, "hyperfocus", teraz=TERAZ + timedelta(hours=1), sciezka=self.db)
        self.assertEqual((b["slowo"], b["notatka"]), ("skupiony", "dobry start"))

    def test_bez_wpisu_z_dzis_brak_osi(self):
        with self.assertRaises(stan.BladStanu) as e:
            stan.ustaw_uwage(W, "hypofocus", teraz=TERAZ, sciezka=self.db)
        self.assertEqual(e.exception.kod, "brak_wpisu")


class Tydzien(Baza):
    def test_siedem_dni_z_lukami_i_ostatni_wpis_dnia(self):
        self.wpis(2, 2, TERAZ - timedelta(days=2))
        self.wpis(-2, -2, TERAZ - timedelta(days=1, hours=1))
        self.wpis(1, 1, TERAZ - timedelta(days=1))                 # późniejszy wpis tego samego dnia wygrywa
        self.wpis(-1, -1, TERAZ - timedelta(days=9))               # poza oknem
        t = stan.tydzien(W, teraz=TERAZ, sciezka=self.db)
        self.assertEqual(len(t), 7)
        self.assertEqual(t[-1]["dzien"], "2026-10-01")
        self.assertEqual([x["cwiartka"] for x in t], [None, None, None, None, "peak", "peak", None])


class Sygnaly(Baza):
    def test_pytanie_raz_dziennie_i_odpowiedz_nie_tworzy_wpisu(self):
        s = stan.zapisz_sygnal(W, "phrase", "bad_day", teraz=TERAZ, sciezka=self.db)
        self.assertEqual((s["zapytano"], s["potwierdzone"]), (0, None))
        self.assertFalse(stan.pytano_dzis(W, "bad_day", teraz=TERAZ, sciezka=self.db))
        stan.oznacz_pytanie(W, s["id"], sciezka=self.db)
        self.assertTrue(stan.pytano_dzis(W, "bad_day", teraz=TERAZ, sciezka=self.db))
        self.assertFalse(stan.pytano_dzis(W, "hyperfocus", teraz=TERAZ, sciezka=self.db))
        self.assertFalse(stan.pytano_dzis(W, "bad_day", teraz=TERAZ + timedelta(days=1), sciezka=self.db))
        stan.odpowiedz_na_pytanie(W, s["id"], False, sciezka=self.db)
        self.assertIsNone(stan.dzisiejszy(W, teraz=TERAZ, sciezka=self.db))   # odpowiedź „nie” niczego nie zapisuje

    def test_odpowiedz_bez_zadanego_pytania_odrzucona(self):
        s = stan.zapisz_sygnal(W, "late_hour", "bad_day", teraz=TERAZ, sciezka=self.db)
        with self.assertRaises(stan.BladStanu):
            stan.odpowiedz_na_pytanie(W, s["id"], True, sciezka=self.db)

    def test_zle_enumy(self):
        with self.assertRaises(stan.BladStanu):
            stan.zapisz_sygnal(W, "x", "bad_day", sciezka=self.db)
        with self.assertRaises(stan.BladStanu):
            stan.zapisz_sygnal(W, "phrase", "x", sciezka=self.db)


if __name__ == "__main__":
    unittest.main()
