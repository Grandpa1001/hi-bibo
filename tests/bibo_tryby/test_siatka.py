"""Siatka stanu w rozmowie: klawiatura, rozpoznanie stuknięć, słowo/notatka, raz dziennie, hooki i /stan."""
import asyncio
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul, wtyczka  # noqa: E402

siatka = podmodul("bibo-tryby", "siatka")
stan = podmodul("bibo-tryby", "stan")
kontakt = podmodul("bibo-tryby", "kontakt")
gm = podmodul("bibo-tryby", "gateway_most")
wt = wtyczka("bibo-tryby")

W = "42"
TERAZ = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
POLE_SZCZYT = "⚡⚡ 😄"        # energia 2, przyjemność 2
POLE_REGEN = "🌙🌙 😣"         # -2, -2


class Baza(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "s.sqlite3"
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": W, "HERMES_HOME": self.tmp.name})
        self.env.start()
        os.environ.pop("BIBO_STREFA", None)
        self.zegar = mock.patch.object(kontakt, "teraz", return_value=TERAZ)
        self.zegar.start()
        wt._siatka_dzien.clear()

    def tearDown(self):
        self.zegar.stop()
        self.env.stop()
        self.tmp.cleanup()

    def o(self, t):
        return siatka.obsluz(W, t, teraz=TERAZ, sciezka=self.db)


class Klawiatura(Baza):
    def test_siatka_4x4_a_kazde_pole_ma_jednoznaczna_cwiartke(self):
        k = siatka.klawiatura_siatki()
        self.assertEqual([len(r) for r in k["keyboard"]], [4, 4, 4, 4])
        self.assertTrue(k["one_time_keyboard"])
        pola = [b["text"] for r in k["keyboard"] for b in r]
        self.assertEqual(len(set(pola)), 16)
        self.assertEqual({stan.cwiartka(*siatka.POLA[t]) for t in pola}, set(stan.CWIARTKI))
        self.assertEqual(siatka.POLA[POLE_SZCZYT], (2, 2))

    def test_rozpoznanie_nie_lapie_zwyklych_wiadomosci(self):
        for t in ("zmęczony", "spokojny", "pomiń", "hej", "😄", "notatka"):
            self.assertFalse(siatka.rozpoznaj(t), t)
        for t in (POLE_SZCZYT, "💭 skupiony", siatka.PRZYCISK_POMIN, "Notatka: coś"):
            self.assertTrue(siatka.rozpoznaj(t), t)


class Przeplyw(Baza):
    def test_tap_zapisuje_i_prosi_o_slowo_z_cwiartki(self):
        odp = self.o(POLE_SZCZYT)
        self.assertIn("Szczyt", odp["text"])
        przyciski = [b["text"] for r in odp["reply_markup"]["keyboard"] for b in r]
        self.assertEqual(przyciski, ["💭 " + s for s in stan.SLOWA["peak"]] + [siatka.PRZYCISK_POMIN]
                         + ["🌫 Rozproszony", "👌 W normie", "🎯 Hiperfokus"])
        self.assertEqual([b["text"] for b in odp["reply_markup"]["keyboard"][-1]],
                         ["🌫 Rozproszony", "👌 W normie", "🎯 Hiperfokus"])   # FR-11: jeden rząd trzech przycisków
        self.assertEqual(stan.dzisiejszy(W, teraz=TERAZ, sciezka=self.db)["cwiartka"], "peak")

    def test_slowo_pomin_i_notatka(self):
        self.o(POLE_REGEN)
        self.assertEqual(self.o("💭 zmęczony")["text"], "Dopisane.")
        self.assertEqual(stan.dzisiejszy(W, teraz=TERAZ, sciezka=self.db)["slowo"], "zmęczony")
        self.assertEqual(self.o("notatka: kiepsko spałem")["text"], "Notatka dopisana.")
        self.assertEqual(stan.dzisiejszy(W, teraz=TERAZ, sciezka=self.db)["notatka"], "kiepsko spałem")
        self.assertIn("zostawiam", self.o(siatka.PRZYCISK_POMIN)["text"])

    def test_slowo_z_innej_cwiartki_nie_zmienia_wpisu(self):
        self.o(POLE_SZCZYT)
        self.assertIn("Nie zapisałem", self.o("💭 wyczerpany")["text"])
        self.assertIsNone(stan.dzisiejszy(W, teraz=TERAZ, sciezka=self.db)["slowo"])

    def test_bez_wpisu_dzis_slowo_pomin_notatka_ida_do_bibo(self):
        for t in ("💭 skupiony", siatka.PRZYCISK_POMIN, "notatka: x"):
            self.assertIsNone(self.o(t), t)

    def test_nowy_tap_zastepuje_tryb(self):
        self.o(POLE_SZCZYT)
        self.o(POLE_REGEN)   # FR-7
        self.assertEqual(stan.dzisiejszy(W, teraz=TERAZ, sciezka=self.db)["cwiartka"], "recovery")

    def test_awaria_zapisu_mowi_ze_nic_nie_zapisano(self):
        with mock.patch.object(stan, "zapisz_wpis", side_effect=RuntimeError("dysk")):
            odp = self.o(POLE_SZCZYT)
        self.assertIn("nic nie zostało zmienione", odp["text"])
        self.assertNotIn("Zapisane", odp["text"])


class Raz_dziennie(Baza):
    def test_siatka_najwyzej_raz_dziennie_i_nie_gdy_jest_wpis(self):
        self.assertTrue(stan.czy_pokazac_siatke(W, teraz=TERAZ, sciezka=self.db))
        self.assertFalse(stan.czy_pokazac_siatke(W, teraz=TERAZ, sciezka=self.db))
        self.assertTrue(stan.czy_pokazac_siatke(W, teraz=TERAZ + timedelta(days=1), sciezka=self.db))
        stan.zapisz_wpis(W, 1, 1, teraz=TERAZ + timedelta(days=2), sciezka=self.db)
        self.assertFalse(stan.czy_pokazac_siatke(W, teraz=TERAZ + timedelta(days=2), sciezka=self.db))


class Hooki(Baza):
    def setUp(self):
        super().setUp()
        self.db = None   # hooki piszą do domyślnej bazy w tymczasowym HERMES_HOME
        self.u = MagicMock()
        self.u.bot = MagicMock()
        self.u.zleć = lambda coro: asyncio.run(coro)
        self.u.bot.wywolaj = AsyncMock(return_value={})
        self.p = [mock.patch.object(wt.uslugi, "aktywne", return_value=self.u),
                  mock.patch.object(gm, "ostatni_user", return_value=W)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        super().tearDown()

    def zdarzenie(self, tekst, uid=W, typ="dm"):
        src = SimpleNamespace(platform=SimpleNamespace(value="telegram"), user_id=uid, chat_id=uid, chat_type=typ)
        return SimpleNamespace(source=src, text=tekst)

    def test_tap_jest_pomijany_i_dostaje_odpowiedz_bota(self):
        r = wt._na_wiadomosc(event=self.zdarzenie(POLE_SZCZYT))
        self.assertEqual(r["action"], "skip")
        self.assertIn("Zapisane", self.u.bot.wywolaj.call_args.args[1]["text"])
        self.assertEqual(self.u.bot.wywolaj.call_args.args[1]["chat_id"], W)

    def test_zwykla_wiadomosc_i_obcy_user_ida_do_bibo(self):
        self.assertIsNone(wt._na_wiadomosc(event=self.zdarzenie("hej")))
        self.assertIsNone(wt._na_wiadomosc(event=self.zdarzenie(POLE_SZCZYT, uid="7")))
        self.assertIsNone(wt._na_wiadomosc(event=self.zdarzenie(POLE_SZCZYT, typ="group")))
        self.u.bot.wywolaj.assert_not_called()

    def test_bez_botu_tap_idzie_do_bibo_i_nic_nie_zapisuje(self):
        self.u.bot = None
        self.assertIsNone(wt._na_wiadomosc(event=self.zdarzenie(POLE_SZCZYT)))

    def test_wylaczone_w_ustawieniach(self):
        with mock.patch.object(siatka.magazyn, "ustawienia", return_value={"stan": False}):
            self.assertIsNone(wt._na_wiadomosc(event=self.zdarzenie(POLE_SZCZYT)))
            wt._po_turze(platform="telegram")
        self.u.bot.wywolaj.assert_not_called()

    def test_po_pierwszej_turze_siatka_raz_potem_cisza(self):
        wt._po_turze(platform="telegram")
        wt._po_turze(platform="telegram")
        self.assertEqual(self.u.bot.wywolaj.call_count, 1)
        self.assertEqual(self.u.bot.wywolaj.call_args.args[1]["text"], siatka.TEKST_SIATKI)

    def test_po_turze_bez_siatki_gdy_jest_wpis_lub_inna_platforma(self):
        stan.zapisz_wpis(W, 1, 1, teraz=TERAZ, sciezka=self.db)
        wt._po_turze(platform="telegram")
        wt._siatka_dzien.clear()
        wt._po_turze(platform="cli")
        self.u.bot.wywolaj.assert_not_called()

    def test_komenda_stan_pokazuje_siatke_nawet_gdy_jest_wpis(self):
        stan.zapisz_wpis(W, 1, 1, teraz=TERAZ, sciezka=self.db)
        self.assertIsNone(wt._komenda_stan(""))
        self.assertEqual(self.u.bot.wywolaj.call_args.args[1]["text"], siatka.TEKST_SIATKI)

    def test_komenda_stan_bez_uslug(self):
        self.u.bot = None
        self.assertIn("za chwilę", wt._komenda_stan(""))


if __name__ == "__main__":
    unittest.main()
