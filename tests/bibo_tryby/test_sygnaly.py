"""Sygnały gorszego dnia / hiperfokusu / hipofokusu, pytania raz dziennie, odpowiedzi, oszacowanie po przerwie, wsparcie."""
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

sygnaly = podmodul("bibo-tryby", "sygnaly")
stan = podmodul("bibo-tryby", "stan")
karta = podmodul("bibo-tryby", "karta")
kontakt = podmodul("bibo-tryby", "kontakt")
siatka = podmodul("bibo-tryby", "siatka")
gm = podmodul("bibo-tryby", "gateway_most")
kryzys = podmodul("bibo-tryby", "kryzys")
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
        self.teraz = TERAZ
        self.zegar = mock.patch.object(kontakt, "teraz", side_effect=lambda: self.teraz)
        self.zegar.start()

    def tearDown(self):
        self.zegar.stop()
        self.env.stop()
        self.tmp.cleanup()

    def wpis(self, e=1, p=1, dt=None, **kw):
        return stan.zapisz_wpis(W, e, p, teraz=dt or self.teraz, sciezka=self.db, **kw)

    def tura(self, tekst="hej", dt=None):
        dt = dt or self.teraz
        self.teraz = dt
        stan.rejestruj_ture(W, teraz=dt, sciezka=self.db)
        return sygnaly.po_turze(W, tekst, teraz=dt, sciezka=self.db, sciezka_karty=self.kdb)

    def odloz_karte(self, tytul):
        """Karta zakończona/odłożona „teraz” wg zegara testu (karta.py ma własny zegar)."""
        teraz_iso = self.teraz.astimezone(kontakt.strefa()).isoformat(timespec="seconds")
        with mock.patch.object(karta, "_teraz", return_value=teraz_iso):
            karta.utworz(W, {"cel": tytul}, sciezka=self.kdb)
            karta.przenies(W, "odlozona", sciezka=self.kdb)

    def rodzaje(self, cel, dt=None):
        return {r["rodzaj"] for r in stan.sygnaly_dzis(W, cel, teraz=dt or self.teraz, sciezka=self.db)}


class GorszyDzien(Baza):
    def test_wyrazna_fraza_wystarcza_sama(self):
        for t in ("nie mam siły", "Nie daję rady z tym", "jestem wykończona", "mam dość"):
            self.setUp_dzien()
            p = self.tura(t)
            self.assertEqual(p["cel"] if p else None, "bad_day", t)

    def setUp_dzien(self):
        self.tearDown()
        self.setUp()

    def test_zwykla_wiadomosc_nic_nie_wywoluje(self):
        self.assertIsNone(self.tura("co dziś robimy z raportem?"))
        self.assertEqual(self.rodzaje("bad_day"), set())

    def test_pora_sama_nie_wystarcza_ale_z_krotkimi_wiadomosciami_tak(self):
        noc = datetime(2026, 10, 1, 21, 30, tzinfo=timezone.utc)   # 23:30 w Warszawie
        for i in range(25):   # typowe tempo: długie wiadomości w poprzednich dniach
            stan.zapisz_dlugosc(W, 120, teraz=noc - timedelta(days=3, minutes=i), sciezka=self.db)
        self.assertIsNone(self.tura("dłuższa wiadomość o planie na jutro, całkiem rozbudowana, żeby nie było krótko", noc))
        self.assertEqual(self.rodzaje("bad_day", noc), {"late_hour"})
        self.tura("ok", noc + timedelta(minutes=1))
        p = self.tura("tak", noc + timedelta(minutes=2))
        self.assertEqual(p["cel"], "bad_day")
        self.assertEqual(self.rodzaje("bad_day", noc), {"late_hour", "short_messages"})

    def test_pytanie_raz_dziennie_i_jedno_naraz(self):
        self.assertEqual(self.tura("nie mam siły")["cel"], "bad_day")
        self.assertIsNone(self.tura("nie daję rady"))                       # już pytano dziś
        self.assertIsNone(self.tura("mam dość", self.teraz + timedelta(hours=1)))
        # następna doba: znów można
        self.assertEqual(self.tura("nie mam siły", self.teraz + timedelta(days=1))["cel"], "bad_day")

    def test_ten_sam_rodzaj_sygnalu_liczy_sie_raz(self):
        self.tura("nie mam siły")
        self.tura("nie mam siły")
        self.assertEqual(len(stan.sygnaly_dzis(W, "bad_day", teraz=self.teraz, sciezka=self.db)), 1)

    def test_nie_pytamy_gdy_user_sam_wybral_regeneracje(self):
        self.wpis(-2, -2)
        self.assertIsNone(self.tura("nie mam siły"))


class Odpowiedzi(Baza):
    def odp(self, t):
        return sygnaly.odpowiedz(W, t, teraz=self.teraz, sciezka=self.db, sciezka_karty=self.kdb)

    def test_tak_na_gorszy_dzien_obniza_tylko_przyjemnosc_i_oznacza_zrodlo(self):
        self.wpis(2, 2)
        self.tura("nie mam siły")
        o = self.odp(sygnaly.TAK)
        d = stan.dzisiejszy(W, teraz=self.teraz, sciezka=self.db)
        self.assertEqual((d["cwiartka"], d["energia"], d["zrodlo"]), ("tension", 2, "inferred_confirmed"))
        self.assertIn("Napięcie", o["text"])
        self.assertTrue(all(r["potwierdzone"] == 1 for r in stan.sygnaly_dzis(W, "bad_day", teraz=self.teraz, sciezka=self.db)))

    def test_tak_bez_wpisu_dzis_tworzy_regeneracje_przy_niskiej_energii_domyslnie(self):
        self.tura("nie mam siły")
        self.odp(sygnaly.TAK)
        self.assertEqual(stan.dzisiejszy(W, teraz=self.teraz, sciezka=self.db)["cwiartka"], "recovery")

    def test_nie_niczego_nie_zapisuje_poza_odpowiedzia_przy_sygnale(self):
        self.wpis(2, 2)
        self.tura("nie mam siły")
        o = self.odp(sygnaly.NIE)
        self.assertIn("bez zmian", o["text"])
        d = stan.dzisiejszy(W, teraz=self.teraz, sciezka=self.db)
        self.assertEqual((d["cwiartka"], d["zrodlo"]), ("peak", "manual"))
        self.assertTrue(all(r["potwierdzone"] == 0 for r in stan.sygnaly_dzis(W, "bad_day", teraz=self.teraz, sciezka=self.db)))
        with stan._polacz(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM wpisy_stanu").fetchone()[0], 1)

    def test_bez_zadanego_pytania_tak_nie_idzie_do_obslugi(self):
        self.assertIsNone(self.odp(sygnaly.TAK))
        self.assertIsNone(siatka.obsluz(W, sygnaly.TAK, teraz=self.teraz, sciezka=self.db))

    def test_odpowiedz_tylko_raz(self):
        self.wpis(2, 2)
        self.tura("nie mam siły")
        self.assertIsNotNone(self.odp(sygnaly.NIE))
        self.assertIsNone(self.odp(sygnaly.TAK))   # pytanie już zamknięte

    def test_przycisk_przez_siatke(self):
        self.wpis(2, 2)
        self.tura("nie mam siły")
        o = siatka.obsluz(W, "❌ Nie", teraz=self.teraz, sciezka=self.db)
        self.assertIn("bez zmian", o["text"])


class Uwaga(Baza):
    def test_hiperfokus_po_sesji_ponad_3h_wymaga_dzisiejszego_wpisu(self):
        self.assertIsNone(self.tura("start"))   # bez wpisu nie pytamy o uwagę
        t = self.teraz
        for i in range(1, 9):   # ciągła sesja co 25 min: 200 min, ponad 3 h
            self.tura("dalej", t + timedelta(minutes=25 * i))
        self.assertEqual(self.rodzaje("hyperfocus"), {"long_session"})
        self.wpis(1, 1, dt=self.teraz)
        p = self.tura("dalej", self.teraz + timedelta(minutes=25))
        self.assertEqual(p["cel"], "hyperfocus")
        self.assertEqual(p["text"], "Jesteś w hiperfokusie?")

    def test_tak_na_hiperfokus_przelacza_uwage_i_nie_pytamy_gdy_juz_jest(self):
        self.wpis(1, 1)
        self.tura("start")
        for i in range(8):
            self.tura("dalej", self.teraz + timedelta(minutes=25))
        o = sygnaly.odpowiedz(W, sygnaly.TAK, teraz=self.teraz, sciezka=self.db, sciezka_karty=self.kdb)
        self.assertIn("hiperfokus", o["text"])
        self.assertEqual(stan.dzisiejszy(W, teraz=self.teraz, sciezka=self.db)["uwaga"], "hyperfocus")

    def test_hipofokus_wymaga_dwoch_rodzajow(self):
        self.wpis(1, 1)
        self.odloz_karte("A")
        self.odloz_karte("B")   # dwie karty odłożone dziś
        self.assertIsNone(self.tura("hej"))
        self.assertEqual(self.rodzaje("hypofocus"), {"abandoned_tasks"})
        with stan._polacz(self.db) as db:   # cztery krótkie sesje (po ~5 min)
            db.execute("UPDATE aktywnosc SET sesje=4, sekundy=1200")
        p = self.tura("hej")
        self.assertEqual(p["cel"], "hypofocus")
        self.assertEqual(p["text"], "Rozproszony dzień?")

    def test_limit_dwoch_pytan_dziennie(self):
        self.wpis(1, 1)
        self.assertEqual(self.tura("nie mam siły")["cel"], "bad_day")
        sygnaly.odpowiedz(W, sygnaly.NIE, teraz=self.teraz, sciezka=self.db, sciezka_karty=self.kdb)
        p = None
        for i in range(9):
            p = self.tura("dalej", self.teraz + timedelta(minutes=25)) or p
        self.assertEqual(p["cel"], "hyperfocus")
        sygnaly.odpowiedz(W, sygnaly.NIE, teraz=self.teraz, sciezka=self.db, sciezka_karty=self.kdb)
        self.odloz_karte("A")
        self.odloz_karte("B")
        with stan._polacz(self.db) as db:
            db.execute("UPDATE aktywnosc SET sesje=4, sekundy=1200")
        self.assertIsNone(self.tura("hej"))   # trzeciego pytania dziś nie będzie


class Oszacowanie(Baza):
    def zapisz_historie(self, dni_temu, cw=(1, 1)):
        for d in dni_temu:
            self.wpis(*cw, dt=TERAZ - timedelta(days=d))

    def test_po_dwoch_pominietych_dniach_jedno_oszacowanie_z_typowym_stanem(self):
        self.zapisz_historie([3], (-1, 1))
        self.zapisz_historie([4, 5], (-2, -2))
        o = sygnaly.oszacowanie(W, teraz=TERAZ, sciezka=self.db)   # 3 doby od wpisu
        self.assertIn("oszacowanie", o["text"])
        self.assertIn("Regeneracja", o["text"])   # najczęstsza w tygodniu
        self.assertIsNone(sygnaly.oszacowanie(W, teraz=TERAZ + timedelta(hours=2), sciezka=self.db))   # raz na przerwę
        self.assertIsNone(sygnaly.oszacowanie(W, teraz=TERAZ + timedelta(days=1), sciezka=self.db))     # bez przypomnień

    def test_zbyt_krotka_przerwa_lub_brak_historii(self):
        self.assertIsNone(sygnaly.oszacowanie(W, teraz=TERAZ, sciezka=self.db))
        self.zapisz_historie([2])
        self.assertIsNone(sygnaly.oszacowanie(W, teraz=TERAZ, sciezka=self.db))

    def test_tak_zapisuje_wpis_inferred_confirmed_nie_pokazuje_siatke(self):
        self.zapisz_historie([3], (2, 2))
        sygnaly.oszacowanie(W, teraz=TERAZ, sciezka=self.db)
        o = sygnaly.odpowiedz(W, sygnaly.NIE, teraz=TERAZ, sciezka=self.db, sciezka_karty=self.kdb)
        self.assertEqual(len(o["reply_markup"]["keyboard"]), 4)   # siatka
        self.assertIsNone(stan.dzisiejszy(W, teraz=TERAZ, sciezka=self.db))
        # nowa przerwa → nowa propozycja; tym razem „tak”
        self.teraz = TERAZ + timedelta(days=10)
        self.zapisz_historie([], (2, 2))
        self.wpis(2, 2, dt=self.teraz - timedelta(days=3))
        sygnaly.oszacowanie(W, teraz=self.teraz, sciezka=self.db)
        sygnaly.odpowiedz(W, sygnaly.TAK, teraz=self.teraz, sciezka=self.db, sciezka_karty=self.kdb)
        d = stan.dzisiejszy(W, teraz=self.teraz, sciezka=self.db)
        self.assertEqual((d["cwiartka"], d["zrodlo"]), ("peak", "inferred_confirmed"))


class Wsparcie(Baza):
    def test_piec_dni_regeneracji_raz_na_dwa_tygodnie(self):
        for d in range(4, 0, -1):
            self.wpis(-2, -2, dt=TERAZ - timedelta(days=d))
        self.assertIsNone(sygnaly.sugestia_wsparcia(W, teraz=TERAZ, sciezka=self.db))   # 4 dni (dziś bez wpisu)
        self.wpis(-2, -2, dt=TERAZ)
        t = sygnaly.sugestia_wsparcia(W, teraz=TERAZ, sciezka=self.db)
        self.assertIn("kimś bliskim", t)
        self.assertIn("specjalist", t)
        self.assertNotIn("depresj", t.lower())   # bez diagnozy
        self.assertIsNone(sygnaly.sugestia_wsparcia(W, teraz=TERAZ + timedelta(hours=1), sciezka=self.db))

    def test_przerwa_w_serii_zeruje_licznik(self):
        for d in (5, 4, 3, 1, 0):
            self.wpis(-2, -2, dt=TERAZ - timedelta(days=d))
        self.assertEqual(stan.regeneracja_z_rzedu(W, teraz=TERAZ, sciezka=self.db), 2)
        self.assertIsNone(sygnaly.sugestia_wsparcia(W, teraz=TERAZ, sciezka=self.db))

    def test_mocne_sygnaly_trzy_potwierdzone_zle_dni(self):
        for d in (1, 2, 3):
            t = TERAZ - timedelta(days=d)
            stan.zapisz_sygnal(W, "phrase", "bad_day", teraz=t, sciezka=self.db)
            stan.oznacz_pytanie_celu(W, "bad_day", teraz=t, sciezka=self.db)
            stan.odpowiedz_na_cel(W, "bad_day", True, teraz=t, sciezka=self.db)
        self.assertIsNotNone(sygnaly.sugestia_wsparcia(W, teraz=TERAZ, sciezka=self.db))


class Hooki(Baza):
    def setUp(self):
        super().setUp()
        self.db = None
        self.kdb = None
        kryzys._dzien.clear()
        kryzys._tura.clear()
        wt._siatka_dzien.clear()
        self.u = MagicMock()
        self.u.bot = MagicMock()
        self.u.bot.wywolaj = AsyncMock(return_value={})
        self.u.zleć = lambda coro: asyncio.run(coro)
        self.p = [mock.patch.object(wt.uslugi, "aktywne", return_value=self.u), mock.patch.object(gm, "ostatni_user", return_value=W)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        super().tearDown()

    def test_pytanie_wychodzi_po_turze_z_klawiatura_tak_nie(self):
        stan.zapisz_wpis(W, 1, 1)
        wt._po_turze(platform="telegram", user_message="nie mam siły")
        dane = self.u.bot.wywolaj.call_args.args[1]
        self.assertEqual(dane["text"], "Gorszy dzień?")
        self.assertEqual([b["text"] for b in dane["reply_markup"]["keyboard"][0]], ["✅ Tak", "❌ Nie"])

    def test_tura_wewnetrzna_i_brak_tekstu_nie_liczy_sie(self):
        stan.zapisz_wpis(W, 1, 1)
        wt._po_turze(platform="telegram", user_message="[bibo-tryby · notatka systemowa] user: nie mam siły")
        wt._po_turze(platform="telegram", user_message=None)
        wt._po_turze(platform="telegram", user_message=[{"type": "image"}])
        self.u.bot.wywolaj.assert_not_called()
        self.assertEqual(stan.sygnaly_dzis(W, "bad_day"), [])

    def test_wewnetrzna_notatka_nie_liczy_sie_do_aktywnosci(self):
        wt._tryb_dnia(W, "zwykła wiadomość")
        wt._tryb_dnia(W, "[bibo-tryby · notatka systemowa, nie wiadomość od usera]\nKontrola sprawy")
        self.assertEqual(stan.zaangazowanie(W)["tury"], 1)

    def test_pierwsza_tura_po_przerwie_oszacowanie_zamiast_siatki(self):
        stan.zapisz_wpis(W, -2, -2, teraz=TERAZ - timedelta(days=3))
        wt._po_turze(platform="telegram", user_message="hej")
        dane = self.u.bot.wywolaj.call_args.args[1]
        self.assertIn("Moje oszacowanie", dane["text"])
        self.assertEqual(self.u.bot.wywolaj.call_count, 1)   # jedna wiadomość, bez siatki obok

    def test_wylaczone_nie_wykrywa(self):
        stan.zapisz_wpis(W, 1, 1)
        with mock.patch.object(siatka.magazyn, "ustawienia", return_value={"stan": False}):
            wt._po_turze(platform="telegram", user_message="nie mam siły")
        self.u.bot.wywolaj.assert_not_called()


if __name__ == "__main__":
    unittest.main()
