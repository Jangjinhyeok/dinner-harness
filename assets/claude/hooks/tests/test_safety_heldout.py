"""Held-out corpus for shell_guard and the secret_scan path extension (ADR-0024).

Added after the rules in shell_guard.py / secret_patterns.json were final and run
once against them; the first-run result is recorded in ADR-0024. Do not tune rules
against this file — if a rule changes because of it, write a new held-out set.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from handlers import secret_scan, shell_guard
from test_safety_corpus import _read_denied


class HeldOut(unittest.TestCase):
    DANGEROUS_COMMANDS = [
        "Remove-Item -LiteralPath 'C:/p/Source' -Recurse", "Get-ChildItem Source -Recurse | Remove-Item -Force",
        "$p='Source'; Remove-Item $p -Recurse", "Remove-Item * -Force",
        "Start-Process cmd -ArgumentList '/c rd /s /q Source'", "robocopy empty Source /MIR",
        "find . -name '*.cpp' -delete", "Clear-Content Source/Main.cpp", "& {Remove-Item Source -Recurse}",
        "git commit --no-verify -am wip", "git -c CORE.HOOKSPATH=x commit -m y", "HUSKY=0 git commit -m wip",
        "git commit -nm wip",
    ]
    DANGEROUS_PATHS = ["D:/keys/id_ecdsa", "C:/proj/Build/Android/debug.keystore", "C:/Users/me/.aws/credentials"]
    # First run (2026-10-15) missed these by design, decided before the run: the names are too
    # generic to block on (hooks/README.md, secret_scan section). Kept visible, not tuned for.
    KNOWN_MISSES = ["C:/proj/Config/Secrets.ini", "C:/proj/service-account.json"]
    BENIGN_COMMANDS = ["Remove-Item Source/Old.h -Force", "Get-ChildItem Content -Recurse | Measure-Object",
                       "git rebase -i HEAD~3", 'git commit -m "chore: -n flag cleanup"', "rm -f build.log",
                       "rg -n 'rd /s' docs"]
    BENIGN_READS = ["C:/proj/Source/Inventory/InventoryKey.cpp", "C:/proj/Docs/keystore-setup.md"]

    def setUp(self):
        self.patterns = secret_scan._load_patterns()

    def test_dangerous_commands(self):
        for command in self.DANGEROUS_COMMANDS:
            with self.subTest(command=command):
                self.assertTrue(shell_guard.classify(command))

    def test_dangerous_paths(self):
        for path in self.DANGEROUS_PATHS:
            with self.subTest(path=path):
                self.assertIsNotNone(secret_scan._scan("Write", {"file_path": path, "content": "x"}, self.patterns))
                self.assertTrue(_read_denied(path))

    def test_benign(self):
        for command in self.BENIGN_COMMANDS:
            with self.subTest(command=command):
                self.assertEqual(shell_guard.classify(command), [])
                for tool in ("Bash", "PowerShell"):
                    self.assertIsNone(secret_scan._scan(tool, {"command": command}, self.patterns))
        for path in self.BENIGN_READS:
            with self.subTest(path=path):
                self.assertIsNone(secret_scan._scan("Write", {"file_path": path, "content": "x"}, self.patterns))
                self.assertFalse(_read_denied(path))


if __name__ == "__main__":
    unittest.main()
