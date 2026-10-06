"""Bezpieczeństwo: treści o samookaleczeniu i myślach samobójczych przerywają planowanie (116 123 / 112)."""
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

kryzys = podmodul("bibo-tryby", "kryzys")
kontakt = podmodul("bibo-tryby", "kontakt")
stan = podmodul("bibo-tryby", "stan")
siatka = podmodul("bibo-tryby", "siatka")
uwaga = podmodul("bibo-tryby", "uwaga")
gm = podmodul("bibo-tryby", "gateway_most")
wt = wtyczka("bibo-tryby")

W = "42"
TERAZ = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


class Wzorce(unittest.TestCase):
    def test_wykrywa_po_polsku_z_i_bez_ogonkow(self):
        for t in ("chcę się zabić", "chce sie zabic", "Nie chcę już żyć", "myślę o samobójstwie", "mam myśli samobójcze",
                  "chcę skończyć ze sobą", "tnę się", "czasem chcę się pociąć", "wolałabym nie żyć", "samookaleczam się",
                  "chcę umrzeć", "nie warto już żyć", "zrobię sobie krzywdę"):
            self.assertTrue(kryzys.wykryj(t), t)

    def test_zwykle_zdania_nie_wywoluja_alarmu(self):
        for t in ("zabić czas do spotkania", "zabiłem się ze śmiechu", "nie mam siły na raport",
                  "chcę żyć zdrowiej", "co dziś robimy", "umarł mi telefon", "kończę ze sobą na dziś plan"):
            self.assertFalse(kryzys.wykryj(t), t)


class Przeplyw(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": W, "HERMES_HOME": self.tmp.name})
        self.env.start()
        os.environ.pop("BIBO_STREFA", None)
        self.teraz = TERAZ
        self.zegar = mock.patch.object(kontakt, "teraz", side_effect=lambda: self.teraz)
        self.zegar.start()
        kryzys._dzien.clear()
        kryzys._tura.clear()
        wt._siatka_dzien.clear()
        self.u = MagicMock()
        self.u.bot = MagicMock()
        self.u.bot.wywolaj = AsyncMock(return_value={})
        self.u.zleć = lambda coro: asyncio.run(coro)
        self.p = [mock.patch.object(wt.uslugi, "aktywne", return_value=self.u),
                  mock.patch.object(gm, "ostatni_user", return_value=W)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.zegar.stop()
        self.env.stop()
        self.tmp.cleanup()
        kryzys._dzien.clear()
        kryzys._tura.clear()

    def zdarzenie(self, tekst, uid=W, typ="dm"):
        src = SimpleNamespace(platform=SimpleNamespace(value="telegram"), user_id=uid, chat_id=uid, chat_type=typ)
        return SimpleNamespace(source=src, text=tekst)

    def test_numery_pomocy_wychodza_od_razu_i_wiadomosc_dalej_idzie_do_bibo(self):
        r = wt._na_wiadomosc(event=self.zdarzenie("nie chcę już żyć"))
        self.assertIsNone(r)   # nie przechwytujemy: Bibo odpowiada ludzko
        tekst = self.u.bot.wywolaj.call_args.args[1]["text"]
        self.assertIn("116 123", tekst)
        self.assertIn("112", tekst)
        self.assertEqual(self.u.bot.wywolaj.call_args.args[1]["chat_id"], W)
        self.assertNotIn("reply_markup", self.u.bot.wywolaj.call_args.args[1])   # żadnych przycisków planowania

    def test_dziala_niezaleznie_od_ustawienia_stan_i_od_wlasciciela(self):
        with mock.patch.object(siatka.magazyn, "ustawienia", return_value={"stan": False}):
            wt._na_wiadomosc(event=self.zdarzenie("chcę się zabić", uid="7"))
        self.assertEqual(self.u.bot.wywolaj.call_args.args[1]["chat_id"], "7")

    def test_grupa_i_notatki_wewnetrzne_nie_wyzwalaja(self):
        wt._na_wiadomosc(event=self.zdarzenie("chcę się zabić", typ="group"))
        wt._na_wiadomosc(event=self.zdarzenie("[bibo-tryby · notatka systemowa] user napisał: chcę się zabić"))
        self.u.bot.wywolaj.assert_not_called()

    def test_kontekst_tury_przerywa_planowanie_potem_lagodniejszy_do_konca_doby(self):
        stan.zapisz_wpis(W, 2, 2)   # tryb Szczyt: „pełny plan” nie może przebić bezpieczeństwa
        wt._na_wiadomosc(event=self.zdarzenie("chcę się zabić"))
        c = wt._przed_tura(platform="telegram", sender_id=W, user_message="chcę się zabić")["context"]
        self.assertIn("Przerwij tryb planowania", c)
        self.assertIn("116 123", c)
        self.assertNotIn("Szczyt", c)
        c2 = wt._przed_tura(platform="telegram", sender_id=W, user_message="no cześć")["context"]
        self.assertIn("Nie planuj dnia", c2)
        self.assertNotIn("Przerwij tryb planowania", c2)
        self.assertNotIn("Szczyt", c2)
        self.teraz = TERAZ + timedelta(days=1)   # następna doba: wszystko wraca do normy
        c3 = (wt._przed_tura(platform="telegram", sender_id=W, user_message="hej") or {}).get("context", "")
        self.assertNotIn("BEZPIECZEŃSTWO", c3)

    def test_w_dobie_kryzysu_brak_siatki_pytan_sugestii_i_przypomnien(self):
        stan.zapisz_wpis(W, 2, 2, uwaga="hyperfocus", teraz=TERAZ - timedelta(hours=5))
        wt._na_wiadomosc(event=self.zdarzenie("nie chcę żyć"))
        self.u.bot.wywolaj.reset_mock()
        wt._po_turze(platform="telegram", user_message="nie mam siły")
        self.assertEqual(asyncio.run(uwaga.sprawdz(self.u, teraz=TERAZ)), 0)
        self.u.bot.wywolaj.assert_not_called()

    def test_wiadomosc_nie_jest_zapisywana_w_stanie(self):
        wt._na_wiadomosc(event=self.zdarzenie("chcę się zabić"))
        with stan._polacz() as db:
            for tabela in ("wpisy_stanu", "sygnaly_stanu", "wiadomosci_dl", "aktywnosc"):
                self.assertEqual(db.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0], 0, tabela)

    def test_awaria_wysylki_nie_przerywa(self):
        self.u.bot.wywolaj = AsyncMock(side_effect=RuntimeError("siec"))
        self.assertIsNone(wt._na_wiadomosc(event=self.zdarzenie("chcę się zabić")))
        self.assertTrue(kryzys.aktywny(W))   # model nadal dostanie polecenie i numery w kontekście


if __name__ == "__main__":
    unittest.main()
