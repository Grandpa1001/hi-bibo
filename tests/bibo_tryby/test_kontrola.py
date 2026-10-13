"""Testy pętli terminów: obsługuje check-iny i przypomnienia uwagi, a awaria jednego nie zatrzymuje drugiego."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent))
from _ladowanie import podmodul  # noqa: E402

kontrola = podmodul("bibo-tryby", "kontrola")


class Petla(unittest.IsolatedAsyncioTestCase):
    async def test_jeden_obieg_wola_checkiny_i_uwage_mimo_bledu(self):
        u = object()
        with patch.object(kontrola.checkin, "sprawdz", AsyncMock(side_effect=RuntimeError("boom"))) as c, \
                patch.object(kontrola.uwaga, "sprawdz", AsyncMock()) as w, \
                patch.object(kontrola.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                await kontrola.petla(u)
        c.assert_awaited_once_with(u)
        w.assert_awaited_once_with(u)


if __name__ == "__main__":
    unittest.main()
