"""Usługi: jednorazowy reset przycisku menu po Mini App."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402

uslugi = podmodul("bibo-tryby", "uslugi")
telegram = podmodul("bibo-tryby", "telegram")


class ResetMenu(unittest.IsolatedAsyncioTestCase):
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

    def _u(self, blad=None):
        u = uslugi.Uslugi()
        u.bot = MagicMock()
        u.bot.zresetuj_menu = AsyncMock(side_effect=blad)
        return u

    async def test_reset_tylko_raz(self):
        u = self._u()
        await u._zresetuj_menu()
        await u._zresetuj_menu()
        u.bot.zresetuj_menu.assert_awaited_once()

    async def test_blad_telegrama_nie_zapisuje_znacznika(self):
        u = self._u(telegram.BladTelegrama("setChatMenuButton: 500", 500))
        await u._zresetuj_menu()
        u2 = self._u()
        await u2._zresetuj_menu()   # próba ponowiona przy następnym starcie
        u2.bot.zresetuj_menu.assert_awaited_once()

    async def test_reset_wola_domyslne_menu(self):
        sesja = MagicMock()
        bot = telegram.BotApi(sesja)
        bot.wywolaj = AsyncMock()
        await bot.zresetuj_menu()
        bot.wywolaj.assert_awaited_once_with("setChatMenuButton", {"menu_button": {"type": "default"}})


if __name__ == "__main__":
    unittest.main()
