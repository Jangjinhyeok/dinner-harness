"""Source-content hygiene gates: hidden unicode in content/assets, MCP template version pins."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import check

REPO = Path(__file__).resolve().parents[2]


class HiddenUnicodeTests(unittest.TestCase):
    def _scan(self, files):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            for rel, data in files.items():
                path = repo / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
            return check.check_hidden_unicode(repo)

    def test_repo_content_and_assets_are_clean(self):
        self.assertEqual(check.check_hidden_unicode(), [])

    def test_flags_every_zero_width_and_bidi_control(self):
        for cp in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF,
                   0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
                   0x2066, 0x2067, 0x2068, 0x2069):
            with self.subTest(cp=f"U+{cp:04X}"):
                found = self._scan({"content/skills/x/SKILL.md": f"ok\nab{chr(cp)}c\n"})
                self.assertEqual(found, [f"content/skills/x/SKILL.md:2:3: U+{cp:04X}"])

    def test_line_numbers_follow_newlines_only(self):
        self.assertEqual(self._scan({"assets/a.md": "a b\x0cc\r\nd\u200b\n"}),
                         ["assets/a.md:2:2: U+200B"])

    def test_leading_bom_is_allowed_but_not_elsewhere(self):
        self.assertEqual(self._scan({"assets/a.md": "\ufeffhello\n"}), [])
        self.assertEqual(self._scan({"assets/a.md": "\ufeff\ufeffhi\n"}), ["assets/a.md:1:2: U+FEFF"])

    def test_neighbouring_and_non_text_files_are_not_flagged(self):
        self.assertEqual(self._scan({
            "content/a.md": "U+2061 ⁡ and U+200E ‎ are out of scope\n",
            "assets/img.bin": b"\x00\xe2\x80\x8b",               # binary (NUL)
            "assets/legacy.txt": "\u200b".encode("utf-16"),       # not UTF-8
            "assets/claude/hooks/logs/x.log": "\u200b\n",          # runtime log
            "assets/__pycache__/x.md": "\u200b\n",
            "docs/outside.md": "\u202e\n",                        # outside the scanned roots
        }), [])

    def test_hidden_unicode_fails_the_cli_without_install(self):
        output = StringIO()
        with mock.patch.object(check, "check_catalog", return_value=({"Skills": 0, "Agents": 0, "Hooks": 0}, [])), \
             mock.patch.object(check, "check_codex_generated", return_value=[]), \
             mock.patch.object(check, "check_hidden_unicode", return_value=["content/a.md:1:1: U+202E"]), \
             redirect_stdout(output):
            self.assertEqual(check.main(["--target", "codex", "--no-install"]), 1)
        self.assertIn("[hidden-unicode] FAIL", output.getvalue())
        self.assertIn("content/a.md:1:1: U+202E", output.getvalue())


class McpTemplateTests(unittest.TestCase):
    def test_template_is_valid_json_and_every_server_asks_for_an_exact_pin(self):
        text = (REPO / "content/templates/mcp.json").read_text(encoding="utf-8")
        servers = json.loads(text)["mcpServers"]
        self.assertTrue(servers)
        for name, server in servers.items():
            with self.subTest(server=name):
                args = " ".join(server["args"])
                self.assertIn("pin an exact package version", args)
                self.assertIn("never @latest", args)


if __name__ == "__main__":
    unittest.main()
