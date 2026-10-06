"""Podsumowanie tygodnia (FR-9, FR-16): rozkłady, wnioski, jednorazowość w tygodniu ISO, Kronika, kolejność wiadomości."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul, wtyczka  # noqa: E402

podsumowanie = podmodul("bibo-tryby", "podsumowanie")
stan = podmodul("bibo-tryby", "stan")
karta = podmodul("bibo-tryby", "karta")
kontakt = podmodul("bibo-tryby", "kontakt")
siatka = podmodul("bibo-tryby", "siatka")
gm = podmodul("bibo-tryby", "gateway_most")
kryzys = podmodul("bibo-tryby", "kryzys")
wt = wtyczka("bibo-tryby")

W = "42"
TERAZ = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)   # środa 10:00 w Warszawie, tydzień ISO 41


def o_godzinie(dni_temu, godzina_lokalna):
    """UTC dla wpisu `dni_temu` dób przed TERAZ o podanej godzinie w Warszawie (CEST = UTC+2)."""
    d = (TERAZ - timedelta(days=dni_temu)).astimezone(kontakt_strefa()).date()
    return datetime(d.year, d.month, d.day, godzina_lokalna, 0, tzinfo=kontakt_strefa()).astimezone(timezone.utc)


def kontakt_strefa():
    return kontakt.strefa()


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

    def wpis(self, dni_temu, e, p, godzina=12, **kw):
        return stan.zapisz_wpis(W, e, p, teraz=o_godzinie(dni_temu, godzina), sciezka=self.db, **kw)

    def uwaga(self, dni_temu, u, godzina):
        return stan.ustaw_uwage(W, u, teraz=o_godzinie(dni_temu, godzina), sciezka=self.db)

    def zbuduj(self, **kw):
        return podsumowanie.zbuduj(W, teraz=TERAZ, sciezka=self.db, sciezka_karty=self.kdb, **kw)

    def zakoncz_karte(self, dni_temu):
        iso = o_godzinie(dni_temu, 13).astimezone(kontakt.strefa()).isoformat(timespec="seconds")
        with mock.patch.object(karta, "_teraz", return_value=iso):
            karta.utworz(W, {"cel": f"s{dni_temu}"}, sciezka=self.kdb)
            karta.przenies(W, "zakonczona", sciezka=self.kdb)


class Rozklady(Baza):
    def test_za_malo_wpisow_brak_podsumowania(self):
        self.assertIsNone(self.zbuduj())
        self.wpis(1, 2, 2)
        self.assertIsNone(self.zbuduj())
        self.wpis(2, 2, 2)
        self.assertIsNotNone(self.zbuduj())

    def test_rozklad_trybow_ostatni_wpis_dnia_i_dni_bez_wpisu(self):
        self.wpis(0, 2, 2, godzina=8)
        self.wpis(0, -2, -2, godzina=18)       # ostatni wpis dnia wygrywa
        self.wpis(1, -1, 1)
        self.wpis(3, 1, -1)
        p = self.zbuduj()
        self.assertEqual(p["tryby"], {"peak": 0, "steady": 1, "tension": 1, "recovery": 1})
        self.assertEqual((p["dni_z_wpisem"], p["dni_bez_wpisu"]), (3, 4))
        self.assertEqual((p["od"], p["do"]), ((TERAZ - timedelta(days=6)).date().isoformat(), TERAZ.date().isoformat()))

    def test_rozklad_uwagi_hiperfokus_bije_rozproszenie_a_norma_to_reszta(self):
        for d in (0, 1, 2, 3):
            self.wpis(d, 1, 1)
        self.uwaga(1, "hyperfocus", 14)
        self.uwaga(2, "hypofocus", 11)
        self.uwaga(2, "hyperfocus", 15)        # tego samego dnia oba: liczy się hiperfokus
        p = self.zbuduj()
        self.assertEqual(p["uwaga"], {"normal": 2, "hypofocus": 0, "hyperfocus": 2})

    def test_okno_nie_siega_dalej_niz_7_dni(self):
        self.wpis(0, 1, 1)
        self.wpis(1, 1, 1)
        self.wpis(7, 2, 2)
        self.assertEqual(sum(self.zbuduj()["tryby"].values()), 2)


class Wnioski(Baza):
    def test_hiperfokus_pora_dnia_najczesciej(self):
        for d in (0, 1, 2, 3):
            self.wpis(d, 1, 1)
        self.uwaga(1, "hyperfocus", 14)
        self.uwaga(2, "hyperfocus", 15)
        self.uwaga(3, "hyperfocus", 9)
        self.assertEqual(self.zbuduj()["wniosek_uwagi"], "Hiperfokus zaczynał się najczęściej po południu (2 z 3 dni).")

    def test_hiperfokus_w_jednym_dniu_to_za_malo_na_wniosek(self):
        for d in (0, 1):
            self.wpis(d, 1, 1)
        self.uwaga(1, "hyperfocus", 14)
        self.assertIsNone(self.zbuduj()["wniosek_uwagi"])

    def test_hiperfokus_o_roznych_porach_bez_udawania_wzorca(self):
        for d in (0, 1):
            self.wpis(d, 1, 1)
            self.uwaga(d, "hyperfocus", 8 if d else 15)
        self.assertEqual(self.zbuduj()["wniosek_uwagi"], "Hiperfokus pojawił się w 2 dniach, o różnych porach.")

    def test_domkniecia_wg_trybu_gdy_jest_wyrazny_lider(self):
        self.wpis(1, -1, 1)    # Stabilnie
        self.wpis(2, -1, 1)    # Stabilnie
        self.wpis(3, 1, -1)    # Napięcie
        for d in (1, 2, 3):
            self.zakoncz_karte(d)
        self.zakoncz_karte(1)  # druga karta w poniedziałku Stabilnie: lider 3 z 4
        p = self.zbuduj()
        self.assertEqual(p["domkniecia"]["steady"], 3)
        self.assertEqual(p["wniosek_trybow"], "Najwięcej zakończonych spraw (3 z 4) przypadło na tryb Stabilnie.")

    def test_remis_domkniec_wpada_na_najczestszy_tryb(self):
        self.wpis(1, -1, 1)
        self.wpis(2, 1, -1)
        self.wpis(3, 1, -1)
        self.zakoncz_karte(1)
        self.zakoncz_karte(2)
        self.assertEqual(self.zbuduj()["wniosek_trybow"], "Najczęstszy tryb tygodnia: Napięcie (2 z 3 dni z wpisem).")

    def test_brak_lidera_brak_wniosku(self):
        self.wpis(1, -1, 1)
        self.wpis(2, 1, -1)
        self.assertIsNone(self.zbuduj()["wniosek_trybow"])


class Tekst(Baza):
    def test_wiadomosc_ma_oba_rozklady_i_wnioski_bez_diagnozy(self):
        for d in (0, 1, 2):
            self.wpis(d, 2, 2)
        self.uwaga(0, "hyperfocus", 14)
        self.uwaga(1, "hyperfocus", 13)
        t = podsumowanie.tekst(self.zbuduj())
        for fragment in ("Twój tydzień (", "Tryby, liczba dni: Szczyt 3", "(bez wpisu: 4)", "Uwaga, liczba dni:", "W normie 1",
                         "Hiperfokus 2", "Najczęstszy tryb tygodnia", "Hiperfokus zaczynał się", "nie ocena", "Kronice"):
            self.assertIn(fragment, t)
        for zakazane in ("depresj", "zaburzen", "choro"):
            self.assertNotIn(zakazane, t.lower())

    def test_zero_dni_nie_pojawiaja_sie_w_rozkladach(self):
        for d in (0, 1):
            self.wpis(d, 2, 2)
        t = podsumowanie.tekst(self.zbuduj())
        self.assertNotIn("Regeneracja 0", t)
        self.assertNotIn("Rozproszony", t)


class RazWTygodniu(Baza):
    def dane(self):
        for d in (1, 2, 3):
            self.wpis(d, 2, 2)

    def wyslij(self, teraz=TERAZ):
        return podsumowanie.do_wyslania(W, teraz=teraz, sciezka=self.db, sciezka_karty=self.kdb)

    def test_raz_na_tydzien_iso_i_zapis_w_kronice(self):
        self.dane()
        t = self.wyslij()
        self.assertIn("Twój tydzień", t)
        self.assertIsNone(self.wyslij(TERAZ + timedelta(hours=3)))
        self.assertIsNone(self.wyslij(TERAZ + timedelta(days=1)))            # czwartek, ten sam tydzień
        with stan._polacz(self.db) as db:
            k = db.execute("SELECT * FROM kronika").fetchall()
            self.assertEqual(len(k), 1)
            self.assertEqual((k[0]["rodzaj"], k[0]["tekst"]), ("tydzien", t))
            self.assertEqual(json.loads(k[0]["dane"])["dni_z_wpisem"], 3)

    def test_nastepny_tydzien_iso_to_nowe_podsumowanie(self):
        self.dane()
        self.assertIsNotNone(self.wyslij())
        nastepny = TERAZ + timedelta(days=7)
        for d in (1, 2):
            stan.zapisz_wpis(W, 1, 1, teraz=nastepny - timedelta(days=d), sciezka=self.db)
        self.assertIsNotNone(self.wyslij(nastepny))

    def test_za_malo_danych_nie_zajmuje_tygodnia(self):
        self.wpis(1, 2, 2)
        self.assertIsNone(self.wyslij())
        self.wpis(2, 2, 2)
        self.assertIsNotNone(self.wyslij())     # po uzupełnieniu danych nadal można dostać podsumowanie

    def test_okno_konczy_sie_wczoraj_dzisiejszy_wpis_go_nie_zmienia(self):
        self.wpis(0, 2, 2)
        self.wpis(1, 2, 2)
        self.assertIsNone(self.wyslij())        # tylko 1 doba z wpisem w oknie do wczoraj

    def test_nie_dwa_razy_przy_rownoleglym_zajeciu(self):
        self.dane()
        wyniki = [stan.zapisz_podsumowanie_tygodnia(W, "2026-W41", "t", "{}", teraz=TERAZ, sciezka=self.db) for _ in range(2)]
        self.assertEqual(wyniki, [True, False])


class Dostarczanie(Baza):
    def setUp(self):
        super().setUp()
        self.db = None
        self.kdb = None
        kryzys._dzien.clear()
        kryzys._tura.clear()
        wt._siatka_dzien.clear()
        wt._podsumowanie_dzien.clear()
        self.u = MagicMock()
        self.u.bot = MagicMock()
        self.u.bot.wywolaj = AsyncMock(return_value={})
        self.u.zleć = lambda coro: asyncio.run(coro)
        self.p = [mock.patch.object(wt.uslugi, "aktywne", return_value=self.u), mock.patch.object(gm, "ostatni_user", return_value=W)]
        for x in self.p:
            x.start()
        for d in (1, 2, 3):
            stan.zapisz_wpis(W, 2, 2, teraz=o_godzinie(d, 12))

    def tearDown(self):
        for x in self.p:
            x.stop()
        super().tearDown()

    def zdarzenie(self, tekst):
        from types import SimpleNamespace
        src = SimpleNamespace(platform=SimpleNamespace(value="telegram"), user_id=W, chat_id=W, chat_type="dm")
        return SimpleNamespace(source=src, text=tekst)

    def test_po_wpisie_z_siatki_najpierw_reakcja_potem_podsumowanie_bez_zdejmowania_klawiatury(self):
        r = wt._na_wiadomosc(event=self.zdarzenie("⚡⚡ 😄"))
        self.assertEqual(r["action"], "skip")
        wywolania = [c.args[1] for c in self.u.bot.wywolaj.call_args_list]
        self.assertEqual(len(wywolania), 2)
        self.assertIn("Zapisane", wywolania[0]["text"])
        self.assertIn("keyboard", wywolania[0]["reply_markup"])
        self.assertIn("Twój tydzień", wywolania[1]["text"])
        self.assertNotIn("reply_markup", wywolania[1])     # klawiatura słów i uwagi zostaje

    def test_drugi_wpis_tego_samego_tygodnia_nie_powtarza(self):
        wt._na_wiadomosc(event=self.zdarzenie("⚡⚡ 😄"))
        self.u.bot.wywolaj.reset_mock()
        wt._na_wiadomosc(event=self.zdarzenie("⚡ 🙂"))
        self.assertEqual(self.u.bot.wywolaj.call_count, 1)

    def test_po_zwyklej_turze_gdy_nie_bylo_okazji_przy_siatce(self):
        stan.zapisz_wpis(W, 1, 1)    # dziś jest wpis: siatki nie będzie
        wt._po_turze(platform="telegram", user_message="cześć")
        self.assertIn("Twój tydzień", self.u.bot.wywolaj.call_args.args[1]["text"])

    def test_w_dobie_kryzysu_i_przy_wylaczonym_stanie_nic_nie_wychodzi(self):
        kryzys.zanotuj(W)
        wt._na_wiadomosc(event=self.zdarzenie("⚡⚡ 😄"))
        wt._po_turze(platform="telegram", user_message="cześć")
        self.assertEqual([c.args[1]["text"] for c in self.u.bot.wywolaj.call_args_list if "tydzień" in c.args[1]["text"]], [])
        kryzys._dzien.clear()
        wt._podsumowanie_dzien.clear()
        self.u.bot.wywolaj.reset_mock()
        with mock.patch.object(siatka.magazyn, "ustawienia", return_value={"stan": False}):
            wt._po_turze(platform="telegram", user_message="cześć")
        self.u.bot.wywolaj.assert_not_called()

    def test_komenda_tydzien_na_zadanie_bez_zapisu_do_kroniki(self):
        t = wt._komenda_tydzien("")
        self.assertIn("Twój tydzień", t)
        with stan._polacz() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM kronika").fetchone()[0], 0)

    def test_komenda_tydzien_bez_danych(self):
        with stan._polacz() as db:
            db.execute("DELETE FROM wpisy_stanu")
        self.assertIn("za mało wpisów", wt._komenda_tydzien(""))


if __name__ == "__main__":
    unittest.main()
