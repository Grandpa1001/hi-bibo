#!/usr/bin/env python3
"""Tests for T007 output sanitization (bibo-clean-output plugin)."""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.join(HERE, "..", "install", "plugins", "bibo-clean-output")
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)


class SanitizationTests(unittest.TestCase):
    """Test output sanitization functions from bibo-clean-output plugin."""

    def setUp(self) -> None:
        """Import plugin functions for testing."""
        try:
            import __init__ as plugin_module
            self.strip_thinking = plugin_module._strip_thinking_tokens
            self.ensure_hi = plugin_module._ensure_hi_prefix
            self.truncate = plugin_module._truncate_to_limit
            self.fallback = plugin_module._fallback_message
        except ImportError as e:
            self.skipTest(f"Cannot import plugin module: {e}")

    def test_strip_thinking_tokens_detects_observe(self) -> None:
        """OBSERVE: prefix should be detected and stripped."""
        text = "OBSERVE: user is tired\nHi, I see you're exhausted, bibo"
        cleaned, stripped = self.strip_thinking(text)
        self.assertIn("Hi, I see you're exhausted", cleaned)
        self.assertIsNotNone(stripped)
        self.assertIn("OBSERVE", stripped)

    def test_strip_thinking_tokens_detects_multiple(self) -> None:
        """Multiple thinking tokens should be stripped."""
        text = "OBSERVE: mood\nTHINK: response strategy\nHi message, bibo\nWAIT: reasoning"
        cleaned, stripped = self.strip_thinking(text)
        self.assertIn("Hi message, bibo", cleaned)
        self.assertEqual(stripped.count("OBSERVE") + stripped.count("THINK") + stripped.count("WAIT"), 3)

    def test_strip_thinking_tokens_no_tokens(self) -> None:
        """Text without tokens should return unchanged."""
        text = "Hi, everything is fine, bibo"
        cleaned, stripped = self.strip_thinking(text)
        self.assertEqual(cleaned, text)
        self.assertIsNone(stripped)

    def test_ensure_hi_prefix_already_present(self) -> None:
        """Text starting with Hi should not be modified."""
        text = "Hi, nice to see you, bibo"
        result, fixed = self.ensure_hi(text, "Bibo")
        self.assertEqual(result, text)
        self.assertFalse(fixed)

    def test_ensure_hi_prefix_case_insensitive(self) -> None:
        """hi/HI/Hi should all be recognized."""
        for variant in ["hi,", "HI,", "Hi,"]:
            text = f"{variant} nice to see you, bibo"
            result, fixed = self.ensure_hi(text, "Bibo")
            self.assertFalse(fixed, f"Should not fix {variant}")

    def test_ensure_hi_prefix_missing(self) -> None:
        """Text not starting with Hi should be fixed."""
        text = "Nice to see you, bibo"
        result, fixed = self.ensure_hi(text, "Bibo")
        self.assertTrue(fixed)
        self.assertTrue(result.startswith("Hi,"))
        self.assertIn("Nice to see you", result)

    def test_truncate_under_limit(self) -> None:
        """Text under limit should be unchanged."""
        text = "Hi, you're doing great, bibo"
        result, excess = self.truncate(text)
        self.assertEqual(result, text)
        self.assertIsNone(excess)

    def test_truncate_over_char_limit(self) -> None:
        """Text over 300 chars should be truncated."""
        text = "Hi, " + "x" * 350 + ", bibo"
        result, excess = self.truncate(text)
        self.assertLessEqual(len(result), 300)
        self.assertIsNotNone(excess)
        self.assertIn("x", excess)

    def test_truncate_over_sentence_limit(self) -> None:
        """Text with >3 sentences should be truncated."""
        text = "Hi, first. Second. Third. Fourth. Fifth, bibo"
        result, excess = self.truncate(text)
        periods = result.count(".")
        self.assertLessEqual(periods, 3)
        self.assertIsNotNone(excess)

    def test_fallback_message_format(self) -> None:
        """Fallback should start with Hi and end with ,name."""
        result = self.fallback("Bibo")
        self.assertTrue(result.startswith("Hi,"))
        self.assertTrue(result.endswith(",bibo"))


if __name__ == "__main__":
    unittest.main()
