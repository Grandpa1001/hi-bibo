"""Stan uwagi: wybór, /fokus, wytyczne dla modelu, powrót z hiperfokusu, przypomnienia co 90 min."""
import asyncio
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul, wtyczka  # noqa: E402

stan = podmodul("bibo-tryby", "stan")
tryb = podmodul("bibo-tryby", "tryb")
uwaga = podmodul("bibo-tryby", "uwaga")
karta = podmodul("bibo-tryby", "karta")
kontakt = podmodul("bibo-tryby", "kontakt")
siatka = podmodul("bibo-tryby", "siatka")
wt = wtyczka("bibo-tryby")

W = "42"
TERAZ = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)   # 10:00 w Warszawie


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

    def wpis(self, e=1, p=1, dt=TERAZ, **kw):
        return stan.zapisz_wpis(W, e, p, teraz=dt, sciezka=self.db, **kw)

    def wybierz(self, u, dt=TERAZ):
        return uwaga.wybierz(W, u, teraz=dt, sciezka=self.db, sciezka_karty=self.kdb)


class Wybor(Baza):
    def test_domyslnie_w_normie_a_wybor_dodaje_wpis_z_tymi_samymi_osiami(self):
        self.assertEqual(self.wpis()["uwaga"], "normal")
        self.assertIn("hiperfokus", self.wybierz("hyperfocus", TERAZ + timedelta(minutes=5)))
        d = stan.dzisiejszy(W, teraz=TERAZ + timedelta(minutes=6), sciezka=self.db)
        self.assertEqual((d["uwaga"], d["cwiartka"]), ("hyperfocus", "peak"))

    def test_ta_sama_wartosc_nie_tworzy_wpisu(self):
        self.wpis()
        self.wybierz("normal")
        with stan._polacz(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM wpisy_stanu").fetchone()[0], 1)

    def test_bez_wpisu_dzis_brak_wpisu(self):
        with self.assertRaises(stan.BladStanu) as e:
            self.wybierz("hypofocus")
        self.assertEqual(e.exception.kod, "brak_wpisu")

    def test_przycisk_z_klawiatury_ustawia_uwage(self):
        self.wpis()
        odp = siatka.obsluz(W, "🎯 Hiperfokus", teraz=TERAZ, sciezka=self.db)
        self.assertIn("Uwaga: hiperfokus", odp["text"])
        self.assertEqual(stan.dzisiejszy(W, teraz=TERAZ, sciezka=self.db)["uwaga"], "hyperfocus")

    def test_argument_komendy(self):
        for t, v in (("hiper", "hyperfocus"), ("Hiperfokus", "hyperfocus"), ("rozproszony", "hypofocus"),
                     ("w normie", "normal"), ("norma", "normal")):
            self.assertEqual(uwaga.z_argumentu(t), v, t)
        self.assertIsNone(uwaga.z_argumentu("xyz"))
        self.assertIsNone(uwaga.z_argumentu(""))


class WyjscieZHiperfokusu(Baza):
    def test_podsumowanie_mowi_tylko_co_zapisane(self):
        karta.utworz(W, {"cel": "Raport", "krok": "Wypisz trzy punkty"}, sciezka=self.kdb)
        self.wpis()
        self.wybierz("hyperfocus", TERAZ + timedelta(minutes=1))
        t = self.wybierz("normal", TERAZ + timedelta(hours=3))
        self.assertIn("Uwaga: w normie.", t)
        self.assertIn("Witaj z powrotem", t)
        self.assertIn("żadnej zakończonej dziś sprawy", t)
        self.assertIn("Czeka: Wypisz trzy punkty.", t)

    def test_bez_karty_i_inne_wyjscia_tez_podsumowuja_a_zwykla_zmiana_nie(self):
        self.wpis()
        self.wybierz("hypofocus")
        self.assertNotIn("Witaj z powrotem", self.wybierz("normal", TERAZ + timedelta(minutes=1)))
        self.wybierz("hyperfocus", TERAZ + timedelta(minutes=2))
        t = self.wybierz("hypofocus", TERAZ + timedelta(minutes=3))
        self.assertIn("W karcie nic na Ciebie nie czeka", t)


class Wytyczne(Baza):
    def test_normal_bez_dodatku_a_oba_stany_dodaja_swoje_zasady(self):
        base = tryb.kontekst({"cwiartka": "peak", "uwaga": "normal"})
        self.assertNotIn("Stan uwagi", base)
        hiper = tryb.kontekst({"cwiartka": "peak", "uwaga": "hyperfocus"})
        self.assertIn("nie przerywaj", hiper)
        self.assertIn("nie dorzucaj nowych tematów ani zadań", hiper)
        hipo = tryb.kontekst({"cwiartka": "peak", "uwaga": "hypofocus"})
        self.assertIn("tylko 1 zadanie", hipo)
        self.assertIn("ok. 15 min", hipo)
        self.assertIn("POMYSŁ", hipo)
        self.assertIn("pierwszeństwo przed liczbą zadań z trybu", hipo)
        self.assertLess(len(hiper), 900)
        self.assertLess(len(hipo), 900)


class Przypomnienia(Baza):
    def zajmij(self, dt, **kw):
        return stan.zajmij_przypomnienie(W, teraz=dt, sciezka=self.db, **kw)

    def test_dopiero_po_90_min_i_potem_co_90(self):
        self.wpis()
        self.wybierz("hyperfocus")
        self.assertFalse(self.zajmij(TERAZ + timedelta(minutes=89)))
        self.assertTrue(self.zajmij(TERAZ + timedelta(minutes=90)))
        self.assertFalse(self.zajmij(TERAZ + timedelta(minutes=91)))      # zajęte atomowo, bez powtórki
        self.assertFalse(self.zajmij(TERAZ + timedelta(minutes=179)))
        self.assertTrue(self.zajmij(TERAZ + timedelta(minutes=180)))

    def test_tylko_w_hiperfokusie(self):
        self.wpis()
        self.assertFalse(self.zajmij(TERAZ + timedelta(hours=5)))
        self.wybierz("hypofocus", TERAZ + timedelta(hours=5))
        self.assertFalse(self.zajmij(TERAZ + timedelta(hours=9)))

    def test_cisza_zuzywa_termin_bez_wysylki_i_bez_limitu(self):
        self.wpis()
        self.wybierz("hyperfocus")
        self.assertFalse(self.zajmij(TERAZ + timedelta(minutes=90), wstrzymane=True))
        self.assertFalse(self.zajmij(TERAZ + timedelta(minutes=100)))     # nie „nadrabia” po ciszy
        self.assertTrue(self.zajmij(TERAZ + timedelta(minutes=180)))

    def test_dzienny_limit(self):
        self.wpis()
        self.wybierz("hyperfocus")
        wyslane = sum(self.zajmij(TERAZ + timedelta(minutes=90 * i)) for i in range(1, 12))
        self.assertEqual(wyslane, stan.MAKS_PRZYPOMNIEN)

    def test_pętla_wysyla_jedna_wiadomosc_do_wlasciciela(self):
        self.wpis()
        self.wybierz("hyperfocus")
        u = MagicMock()
        u.bot.wywolaj = AsyncMock(return_value={})
        n = asyncio.run(uwaga.sprawdz(u, teraz=TERAZ + timedelta(minutes=95), sciezka=self.db))
        self.assertEqual(n, 1)
        self.assertEqual(u.bot.wywolaj.call_args.args[1], {"chat_id": W, "text": uwaga.TEKST_PRZERWY})
        self.assertEqual(asyncio.run(uwaga.sprawdz(u, teraz=TERAZ + timedelta(minutes=96), sciezka=self.db)), 0)

    def test_blad_wysylki_nie_ponawia(self):
        self.wpis()
        self.wybierz("hyperfocus")
        u = MagicMock()
        u.bot.wywolaj = AsyncMock(side_effect=RuntimeError("siec"))
        self.assertEqual(asyncio.run(uwaga.sprawdz(u, teraz=TERAZ + timedelta(minutes=95), sciezka=self.db)), 0)
        self.assertEqual(asyncio.run(uwaga.sprawdz(u, teraz=TERAZ + timedelta(minutes=96), sciezka=self.db)), 0)
        self.assertEqual(u.bot.wywolaj.call_count, 1)

    def test_pauza_i_wylaczenie_blokuja(self):
        self.wpis()
        self.wybierz("hyperfocus")
        u = MagicMock()
        u.bot.wywolaj = AsyncMock(return_value={})
        with mock.patch.object(kontakt, "powod_blokady", return_value="pauza"):
            self.assertEqual(asyncio.run(uwaga.sprawdz(u, teraz=TERAZ + timedelta(minutes=95), sciezka=self.db)), 0)
        with mock.patch.object(siatka.magazyn, "ustawienia", return_value={"stan": False}):
            self.assertEqual(asyncio.run(uwaga.sprawdz(u, teraz=TERAZ + timedelta(minutes=200), sciezka=self.db)), 0)
        u.bot.wywolaj.assert_not_called()


class Komenda(Baza):
    def setUp(self):
        super().setUp()
        self.u = MagicMock()
        self.u.bot = MagicMock()
        self.u.zleć = lambda coro: asyncio.run(coro)
        self.u.bot.wywolaj = AsyncMock(return_value={})
        self.p = mock.patch.object(wt.uslugi, "aktywne", return_value=self.u)
        self.p.start()

    def tearDown(self):
        self.p.stop()
        super().tearDown()

    def test_z_argumentem_ustawia_od_razu(self):
        stan.zapisz_wpis(W, 1, 1)   # domyślna baza w tymczasowym HERMES_HOME
        self.assertIn("hiperfokus", wt._komenda_fokus("hiper"))
        self.assertEqual(stan.dzisiejszy(W)["uwaga"], "hyperfocus")

    def test_bez_argumentu_pokazuje_rzad_przyciskow(self):
        stan.zapisz_wpis(W, 1, 1)
        self.assertIsNone(wt._komenda_fokus(""))
        k = self.u.bot.wywolaj.call_args.args[1]["reply_markup"]["keyboard"]
        self.assertEqual([len(r) for r in k], [3])

    def test_bez_wpisu_najpierw_siatka(self):
        self.assertIsNone(wt._komenda_fokus(""))
        self.assertIsNone(wt._komenda_fokus("hiper"))
        for c in self.u.bot.wywolaj.call_args_list:
            self.assertEqual(len(c.args[1]["reply_markup"]["keyboard"]), 4)   # siatka 4×4
        self.assertIsNone(stan.dzisiejszy(W))

    def test_zly_argument(self):
        self.assertIn("Podaj", wt._komenda_fokus("xyz"))


if __name__ == "__main__":
    unittest.main()
