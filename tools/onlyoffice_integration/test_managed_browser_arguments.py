"""Browser callers cannot inject switches or select a foreign profile."""

import unittest
from pathlib import Path

from .managed_browser_arguments import CHROMIUM_ARGUMENTS, browser_arguments


class TestManagedBrowserArguments(unittest.TestCase):
    def setUp(self):
        self.directory = Path("/owned/attempt")
        self.arguments = [
            *CHROMIUM_ARGUMENTS,
            "--user-data-dir=/owned/attempt/browser-profile",
            "--remote-debugging-pipe",
            "about:blank",
        ]

    def test_pinned_launch_is_reconstructed_without_caller_arguments(self):
        result = browser_arguments(self.arguments, self.directory)
        self.assertEqual(result, self.arguments)
        self.assertIsNot(result, self.arguments)

    def test_security_bypasses_urls_and_foreign_profiles_are_refused(self):
        for argument in (
            "--no-sandbox",
            "--disable-web-security",
            "--ignore-certificate-errors",
            "--remote-debugging-port=9222",
            "https://foreign.invalid",
        ):
            with self.subTest(argument=argument), self.assertRaises(RuntimeError):
                browser_arguments([*self.arguments, argument], self.directory)
        foreign = [
            argument.replace("/owned/attempt", "/foreign")
            for argument in self.arguments
        ]
        with self.assertRaises(RuntimeError):
            browser_arguments(foreign, self.directory)
