"""Check-in: zapis terminu, przejęcie, wysyłka, pauza/cisza, anulowanie, restart (kontrolowany zegar, atrapa Bot API)."""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402

karta = podmodul("bibo-tryby", "karta")
checkin = podmodul("bibo-tryby", "checkin")
kontakt = podmodul("bibo-tryby", "kontakt")
nar = podmodul("bibo-tryby", "karta_narzedzie")
magazyn = podmodul("bibo-tryby", "magazyn")
BladTelegrama = podmodul("bibo-tryby", "telegram").BladTelegrama

W = "42"
# 14:00 w Warszawie (CEST) — cisza 22–8 jest daleko
TERAZ = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class Baza(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "k.sqlite3"
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": W, "HERMES_HOME": self.tmp.name})
        self.env.start()
        os.environ.pop("BIBO_STREFA", None)
        self.zegar = mock.patch.object(kontakt, "teraz", return_value=TERAZ)
        self.zegar.start()
        karta.utworz(W, {"cel": "Raport", "krok": "Wypisz trzy punkty"}, sciezka=self.db)

    def tearDown(self):
        self.zegar.stop()
        self.env.stop()
        self.tmp.cleanup()

    def ustaw(self, **kw):
        return checkin.ustaw(W, teraz=TERAZ, sciezka=self.db, **kw)

    def statusy(self):
        with sqlite3.connect(self.db) as c:
            return [r[0] for r in c.execute("SELECT status FROM checkiny ORDER BY utworzono, rowid")]

    def uslugi(self, wywolaj=None):
        u = MagicMock()
        u.bot.wywolaj = wywolaj or AsyncMock(return_value={"message_id": 77})
        return u

    def sprawdz(self, u, teraz):
        return asyncio.run(checkin.sprawdz(u, teraz=teraz, sciezka=self.db))


class Ustawianie(Baza):
    def test_za_minut_i_potwierdzenie_z_data_w_strefie_usera(self):
        c = self.ustaw(za_minut=90)
        self.assertEqual((c["status"], c["termin"]), ("oczekuje", "dziś, 15:30"))

    def test_godzina_jutro_i_minela(self):
        with self.assertRaises(karta.BladKarty) as e:
            self.ustaw(godzina="09:00")                       # dziś już po 09:00
        self.assertEqual(e.exception.kod, "dane")
        self.assertEqual(self.ustaw(godzina="09:00", data="2026-10-02")["termin"], "jutro, 09:00")

    def test_niejasny_czas(self):
        for kw in ({}, {"godzina": "za chwilę"}, {"za_minut": 0}, {"za_minut": "20"}, {"godzina": "25:00"}):
            with self.assertRaises(karta.BladKarty, msg=kw):
                self.ustaw(**kw)
        self.assertEqual(self.statusy(), [])

    def test_cisza_nocna_wymaga_innego_terminu(self):
        with self.assertRaises(karta.BladKarty) as e:
            self.ustaw(za_minut=10 * 60)                      # 00:00 czasu lokalnego
        self.assertEqual(e.exception.kod, "cisza")
        self.assertEqual(self.statusy(), [])

    def test_pauza_obejmuje_termin(self):
        kontakt.ustaw_pauze(5, TERAZ)
        with self.assertRaises(karta.BladKarty) as e:
            self.ustaw(za_minut=60)
        self.assertEqual(e.exception.kod, "pauza")

    def test_jeden_oczekujacy_zastapienie_po_decyzji(self):
        self.ustaw(za_minut=30)
        with self.assertRaises(karta.BladKarty) as e:
            self.ustaw(za_minut=60)
        self.assertEqual(e.exception.kod, "jest_checkin")
        self.assertIn("dziś, 14:30", e.exception.komunikat)
        self.assertEqual(self.ustaw(za_minut=60, zastap=True)["termin"], "dziś, 15:00")
        self.assertEqual(self.statusy(), ["anulowany", "oczekuje"])

    def test_wymaga_aktywnej_karty(self):
        karta.przenies(W, "odlozona", sciezka=self.db)
        with self.assertRaises(karta.BladKarty) as e:
            self.ustaw(za_minut=30)
        self.assertEqual(e.exception.kod, "brak_karty")

    def test_wylaczone_w_ustawieniach(self):
        magazyn.zapisz("ustawienia.json", {"checkiny": False})
        with self.assertRaises(karta.BladKarty) as e:
            self.ustaw(za_minut=30)
        self.assertEqual(e.exception.kod, "wylaczone")

    def test_obcy_user_nie_widzi_ani_nie_anuluje(self):
        self.ustaw(za_minut=30)
        self.assertIsNone(checkin.oczekujacy("7", self.db, TERAZ))
        with self.assertRaises(karta.BladKarty):
            checkin.anuluj("7", self.db)
        self.assertEqual(self.statusy(), ["oczekuje"])


class Cykl(Baza):
    def test_przed_terminem_nic(self):
        self.ustaw(za_minut=30)
        self.assertEqual(checkin.przejmij(TERAZ + timedelta(minutes=29), self.db), [])

    def test_przejecie_jest_atomowe_dwa_odczyty_jedno_zadanie(self):
        self.ustaw(za_minut=30)
        t = TERAZ + timedelta(minutes=31)
        pierwsze, drugie = checkin.przejmij(t, self.db), checkin.przejmij(t, self.db)
        self.assertEqual((len(pierwsze), len(drugie)), (1, 0))
        self.assertEqual((pierwsze[0]["wlasciciel"], pierwsze[0]["proby"], self.statusy()), (W, 1, ["wysylanie"]))

    def test_anulowanie_przed_wysylka_skuteczne(self):
        self.ustaw(za_minut=30)
        checkin.anuluj(W, self.db)
        u = self.uslugi()
        self.assertEqual(self.sprawdz(u, TERAZ + timedelta(minutes=31)), 0)
        u.bot.wywolaj.assert_not_awaited()
        self.assertEqual(self.statusy(), ["anulowany"])

    def test_anulowanie_po_przejeciu_uczciwie_odmawia(self):
        self.ustaw(za_minut=30)
        checkin.przejmij(TERAZ + timedelta(minutes=31), self.db)
        with self.assertRaises(karta.BladKarty) as e:
            checkin.anuluj(W, self.db)
        self.assertEqual(e.exception.kod, "juz_wysylane")

    def test_odlozenie_i_zakonczenie_karty_anuluja_termin(self):
        for status in ("odlozona", "zakonczona"):
            with self.subTest(status):
                self.ustaw(za_minut=30, zastap=True)
                karta.przenies(W, status, sciezka=self.db)
                self.assertEqual(checkin.przejmij(TERAZ + timedelta(minutes=31), self.db), [])
                self.assertNotIn("oczekuje", self.statusy())
                if status == "odlozona":
                    karta.przenies(W, "aktywna", sciezka=self.db)    # wznowienie nie przywraca terminu
                    self.assertIsNone(checkin.oczekujacy(W, self.db, TERAZ))

    def test_usuniecie_karty_kasuje_rekord_checkinu(self):
        self.ustaw(za_minut=30)
        karta.usun(W, sciezka=self.db)
        self.assertEqual(self.statusy(), [])

    def test_nowa_sprawa_z_decyzja_anuluje_poprzedni_checkin(self):
        self.ustaw(za_minut=30)
        karta.utworz(W, {"cel": "B"}, poprzednia="odloz", sciezka=self.db)
        self.assertEqual(self.statusy(), ["anulowany"])

    def test_restart_stary_termin_wygasa_bez_wysylki(self):
        self.ustaw(za_minut=30)
        u = self.uslugi()
        self.assertEqual(self.sprawdz(u, TERAZ + timedelta(minutes=30 + checkin.MAKS_SPOZNIENIE_MIN + 1)), 0)
        u.bot.wywolaj.assert_not_awaited()
        self.assertEqual(self.statusy(), ["wygasly"])

    def test_pauza_w_chwili_wysylki_pomija_i_wznowienie_nie_wysyla(self):
        self.ustaw(za_minut=30)
        kontakt.ustaw_pauze(2, TERAZ)                         # ustawiona po zaplanowaniu
        u = self.uslugi()
        self.assertEqual(self.sprawdz(u, TERAZ + timedelta(minutes=31)), 0)
        self.assertEqual(self.statusy(), ["pominiety"])
        kontakt.zakoncz_pauze()
        self.assertEqual(self.sprawdz(u, TERAZ + timedelta(minutes=40)), 0)
        u.bot.wywolaj.assert_not_awaited()

    def test_cisza_w_chwili_wysylki_pomija(self):
        self.ustaw(za_minut=30)
        (Path(self.tmp.name) / "local").mkdir(exist_ok=True)
        (Path(self.tmp.name) / "local" / "bibo_pulse.json").write_text(json.dumps({"quiet_from": 14, "quiet_to": 16}))
        self.assertEqual(self.sprawdz(self.uslugi(), TERAZ + timedelta(minutes=31)), 0)
        self.assertEqual(self.statusy(), ["pominiety"])

    def test_wylaczenie_funkcji_oprozsnia_kolejke(self):
        self.ustaw(za_minut=30)
        magazyn.zapisz("ustawienia.json", {"checkiny": False})
        u = self.uslugi()
        self.assertEqual(self.sprawdz(u, TERAZ + timedelta(minutes=31)), 0)
        self.assertEqual(self.statusy(), ["anulowany"])
        u.bot.wywolaj.assert_not_awaited()


class Wysylka(Baza):
    def test_wysyla_raz_do_wlasciciela_i_nie_ponagla(self):
        self.ustaw(za_minut=30)
        u = self.uslugi()
        t = TERAZ + timedelta(minutes=31)
        with mock.patch.object(checkin.gateway_most, "zostaw_notatke") as notatka:
            self.assertEqual(self.sprawdz(u, t), 1)
        metoda, dane = u.bot.wywolaj.await_args.args
        self.assertEqual((metoda, dane["chat_id"]), ("sendMessage", W))
        self.assertIn("Wypisz trzy punkty", dane["text"])
        self.assertEqual([b["text"] for b in dane["reply_markup"]["keyboard"][0]], ["Ruszyłem", "Utknąłem", "Odkładam"])
        self.assertNotIn("parse_mode", dane)
        notatka.assert_called_once()
        self.assertEqual(self.statusy(), ["wyslany"])
        # brak odpowiedzi usera: kolejne przebiegi nic nie wysyłają
        for minuty in (45, 120, 600):
            self.assertEqual(self.sprawdz(u, TERAZ + timedelta(minutes=minuty)), 0)
        u.bot.wywolaj.assert_awaited_once()

    def test_jednoznaczny_blad_ponawia_ograniczona_liczbe_razy(self):
        self.ustaw(za_minut=30)
        u = self.uslugi(AsyncMock(side_effect=BladTelegrama("sendMessage: 400 bad", 400)))
        for i in range(6):
            self.sprawdz(u, TERAZ + timedelta(minutes=31 + i))
        self.assertEqual(u.bot.wywolaj.await_count, checkin.MAKS_PROBY)
        self.assertEqual(self.statusy(), ["blad"])

    def test_niejednoznaczny_blad_nie_ponawia(self):
        for blad in (asyncio.TimeoutError(), BladTelegrama("sendMessage: 502", 502), RuntimeError("siec")):
            with self.subTest(type(blad).__name__):
                checkin.anuluj_wszystkie(sciezka=self.db)
                self.ustaw(za_minut=30, zastap=True)
                u = self.uslugi(AsyncMock(side_effect=blad))
                self.sprawdz(u, TERAZ + timedelta(minutes=31))
                self.sprawdz(u, TERAZ + timedelta(minutes=33))
                u.bot.wywolaj.assert_awaited_once()
                self.assertEqual(self.statusy()[-1], "niepewny")
                with sqlite3.connect(self.db) as c:
                    c.execute("DELETE FROM checkiny")

    def test_brak_bota_nic_nie_przejmuje(self):
        self.ustaw(za_minut=30)
        u = MagicMock(bot=None)
        self.assertEqual(self.sprawdz(u, TERAZ + timedelta(minutes=31)), 0)
        self.assertEqual(self.statusy(), ["oczekuje"])

    def test_usuniecie_karty_w_trakcie_wysylki_nie_odtwarza_rekordu(self):
        self.ustaw(za_minut=30)

        async def wywolaj(*a, **k):
            karta.usun(W, sciezka=self.db)                     # user usuwa sprawę, gdy wiadomość wychodzi
            return {"message_id": 5}
        self.sprawdz(self.uslugi(wywolaj), TERAZ + timedelta(minutes=31))
        self.assertEqual(self.statusy(), [])
        self.assertIsNone(karta.aktywna(W, self.db))

    def test_anulowanie_w_trakcie_wysylki_jest_odrzucone(self):
        self.ustaw(za_minut=30)
        wynik = {}

        async def wywolaj(*a, **k):
            try:
                checkin.anuluj(W, self.db)
            except karta.BladKarty as e:
                wynik["kod"] = e.kod
            return {"message_id": 5}
        self.sprawdz(self.uslugi(wywolaj), TERAZ + timedelta(minutes=31))
        self.assertEqual((wynik["kod"], self.statusy()), ("juz_wysylane", ["wyslany"]))

    def test_zawieszone_wysylanie_po_padzie_procesu_to_niepewny(self):
        self.ustaw(za_minut=30)
        checkin.przejmij(TERAZ + timedelta(minutes=31), self.db)      # proces pada przed wysyłką
        u = self.uslugi()
        self.sprawdz(u, TERAZ + timedelta(minutes=31 + checkin.ZAWIESZONE_MIN + 1))
        u.bot.wywolaj.assert_not_awaited()
        self.assertEqual(self.statusy(), ["niepewny"])

    def test_tekst_wiadomosci(self):
        self.assertEqual(checkin.tekst_wiadomosci({"krok": "Wypisz trzy punkty", "cel": "R"}),
                         "Wracamy do: Wypisz trzy punkty. Jak poszło? Możesz odpisać własnymi słowami.")
        self.assertIn("tej sprawy", checkin.tekst_wiadomosci({"krok": "", "cel": ""}))
        self.assertLessEqual(len(checkin.tekst_wiadomosci({"krok": "x" * 300, "cel": ""})), 140)


class Narzedzie(Baza):
    def N(self, **a):
        return json.loads(nar.obsluz(a, sciezka=self.db))

    def test_potwierdzenie_tylko_po_zapisie(self):
        r = self.N(akcja="checkin_ustaw", za_minut=20)
        self.assertTrue(r["ok"])
        self.assertRegex(r["potwierdzenie"], r"^Zaplanowane na (dziś|jutro|\w+ \d\d\.\d\d), \d\d:\d\d\. Możesz anulować\.$")
        self.assertEqual(self.statusy(), ["oczekuje"])

    def test_blad_nie_zawiera_potwierdzenia(self):
        with mock.patch.object(checkin, "_polacz", side_effect=RuntimeError("dysk")):
            r = self.N(akcja="checkin_ustaw", za_minut=20)
        self.assertEqual((r["ok"], "potwierdzenie" in r), (False, False))
        self.assertEqual(self.statusy(), [])

    def test_anuluj_i_brak(self):
        self.N(akcja="checkin_ustaw", za_minut=20)
        self.assertTrue(self.N(akcja="checkin_anuluj")["ok"])
        self.assertEqual(self.N(akcja="checkin_anuluj")["blad"], "brak_checkinu")

    def test_pauza_przez_narzedzie_i_walidacja(self):
        self.assertFalse(self.N(akcja="pauza", pauza_godzin=0)["ok"])
        self.assertFalse(self.N(akcja="pauza")["ok"])
        self.assertTrue(self.N(akcja="pauza", pauza_godzin=2)["ok"])
        self.assertIsNotNone(kontakt.pauza_do())
        self.assertTrue(self.N(akcja="koniec_pauzy")["ok"])
        self.assertIsNone(kontakt.pauza_do())

    def test_podsumowanie_pokazuje_checkin_i_pauze(self):
        self.N(akcja="checkin_ustaw", za_minut=20)
        self.N(akcja="pauza", pauza_godzin=1)
        t = nar.podsumowanie(W, self.db)
        self.assertIn("Uzgodniony check-in:", t)
        self.assertIn("Pauza w kontakcie", t)


class Schemat(unittest.TestCase):
    def test_kopia_bazy_przed_dodaniem_tabeli(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"HERMES_HOME": d}):
            db = Path(d) / "k.sqlite3"
            c = sqlite3.connect(db)
            c.execute("CREATE TABLE karty (id TEXT, wlasciciel TEXT, cel TEXT, przeszkoda TEXT, krok TEXT, zatrzymanie TEXT, "
                      "status TEXT, zaktualizowano TEXT, wersja INTEGER DEFAULT 1)")
            c.execute("INSERT INTO karty VALUES ('k_1','42','stary cel','','','','aktywna','x',1)")
            c.commit()
            c.close()
            karta._polacz(db).close()
            kopia = db.with_name(db.name + ".przed-checkinami")
            self.assertTrue(kopia.exists())
            self.assertEqual(sqlite3.connect(kopia).execute("SELECT cel FROM karty").fetchone()[0], "stary cel")
            self.assertEqual(sqlite3.connect(db).execute("SELECT count(*) FROM checkiny").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
