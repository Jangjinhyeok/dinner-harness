"""Tuning corpus for shell_guard (destructive commands, git hook bypass) and the
secret_scan sensitive-path extension.

This is the TUNING set: rules were written against it. The held-out set lives in
test_safety_heldout.py and was only added after the rules were final.

Cases in the ``Ecc*`` classes are adapted from affaan-m/ECC (MIT License,
Copyright (c) 2026 Affaan Mustafa), commit b92f181:
  tests/lib/powershell-destructive-command.test.js
  tests/hooks/block-no-verify.test.js
Deliberate deviation: ECC flags a bare ``-Force`` on Remove-Item; shell_guard does
not (single-file force deletes are routine), so ported ``-Force`` cases use
``-Recurse`` where the case is about something else.
"""
import base64
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from handlers import secret_scan, shell_guard

_TEMPLATE = Path(__file__).resolve().parents[2] / "settings.json.template"


def _deny_rules():
    return json.loads(_TEMPLATE.read_text(encoding="utf-8"))["permissions"]["deny"]


def _read_glob_regex(glob):
    """Approximate a ``Read(**/...)`` deny glob as a regex over a /-path.

    Claude Code's own matcher is not available offline; this mirrors gitignore-style
    semantics (``**/`` = any directory prefix, ``*`` = within one segment).
    """
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif glob[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(glob[i])
            i += 1
    return re.compile(out + "$")


def _read_denied(path):
    """Only filesystem-wide ``Read(//...)`` rules are modelled: a bare ``**/`` rule is
    anchored at the session cwd (code.claude.com/docs/en/permissions), so it cannot be
    relied on for ``~/.ssh`` and similar paths outside the project."""
    path = path.replace("\\", "/")
    path = path[0].lower() + path[2:] if path[1:2] == ":" else path  # C:/x -> c/x (doc'd /c/x normalisation)
    for rule in _deny_rules():
        m = re.fullmatch(r"Read\(//(.+)\)", rule)
        # Case-sensitive on purpose: Claude Code's case handling on Windows is not documented,
        # so `cert.PEM` is not claimed as covered.
        if m and _read_glob_regex(m.group(1)).match(path.lstrip("/")):
            return True
    return False


class _Base(unittest.TestCase):
    def assertFlagged(self, command, cwd=None):
        self.assertTrue(shell_guard.classify(command, cwd), f"not flagged: {command!r}")

    def assertClean(self, command, cwd=None):
        self.assertEqual(shell_guard.classify(command, cwd), [], f"flagged: {command!r}")


class DestructiveTuning(_Base):
    CASES = [
        "rm -rf build", "rm -fr ./src", "rm -r -f src", "Remove-Item src -Recurse -Force",
        "Remove-Item -Path src -Recurse", "rm -r -fo src", "ri src -Recurse", "del src -Recurse",
        "rmdir src -r", "Remove-Item src -rec -force", "cmd /c rd /s /q src",
        "cmd /c del /s /q *.cpp", "rd /s /q Source", "Get-ChildItem src | Remove-Item -Recurse",
        "[IO.Directory]::Delete('C:/p/Source', $true)", '[System.IO.Directory]::Delete("Source",$true)',
        "Format-Volume -DriveLetter D", "Remove-Item `-Recurse src",
        'pwsh -c "Remove-Item src -Recurse"', "iex 'Remove-Item src -Recurse'",
    ]

    def test_destructive_commands_are_flagged(self):
        for command in self.CASES:
            with self.subTest(command=command):
                self.assertFlagged(command)

    def test_extra_rules_not_in_ecc(self):
        self.assertIn("robocopy.mirror", shell_guard.classify("robocopy C:/empty C:/proj/Content /MIR"))
        self.assertIn("robocopy.mirror", shell_guard.classify("robocopy a b /purge /e"))
        self.assertIn("find.delete", shell_guard.classify("find build -type f -delete"))
        self.assertIn("find.delete", shell_guard.classify("find . -name '*.o' -exec rm -f {} ;"))
        self.assertClean("robocopy Content Backup /E")
        self.assertClean("find Source -name '*.h'")


class GitBypassTuning(_Base):
    CASES = [
        "git commit -m 'wip' --no-verify", "git push --no-verify", "git commit -n -m wip",
        "git -c core.hooksPath=/dev/null commit -m x", "git -c core.hooksPath= push",
        "git config core.hooksPath .nohooks", "git -c include.path=evil.cfg commit -m x",
    ]

    def test_git_hook_bypass_is_flagged(self):
        for command in self.CASES:
            with self.subTest(command=command):
                self.assertFlagged(command)

    def test_git_config_reads_and_unsets_are_clean(self):
        for command in ("git config --get core.hooksPath", "git config --unset core.hooksPath",
                        "git config core.hooksPath", "git config user.name Someone"):
            with self.subTest(command=command):
                self.assertClean(command)


class CleanupAllowlist(_Base):
    UE = ["Remove-Item Intermediate -Recurse -Force", "rd /s /q Binaries",
          "Remove-Item DerivedDataCache -Recurse", "Remove-Item Saved/Logs -Recurse"]
    UNITY = ["rm -rf Library", "Remove-Item obj -Recurse -Force"]

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.ue = root / "Game"
        self.ue.mkdir()
        (self.ue / "Game.uproject").write_text("{}", encoding="utf-8")
        self.unity = root / "Proj"
        (self.unity / "ProjectSettings").mkdir(parents=True)
        (self.unity / "ProjectSettings" / "ProjectVersion.txt").write_text("m_EditorVersion: 6000.0.0f1",
                                                                          encoding="utf-8")
        self.plain = root / "plain"
        self.plain.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_engine_cleanup_is_allowed_only_at_a_marked_project_root(self):
        for command in self.UE:
            with self.subTest(command=command):
                self.assertClean(command, self.ue)
                self.assertFlagged(command, self.plain)
                self.assertFlagged(command, self.unity)
        for command in self.UNITY:
            with self.subTest(command=command):
                self.assertClean(command, self.unity)
                self.assertFlagged(command, self.plain)

    def test_allowlist_requires_every_target_to_be_exact(self):
        self.assertClean(f"Remove-Item {self.ue.as_posix()}/Intermediate -Recurse", self.ue)
        self.assertClean("Remove-Item ./Intermediate/ -Recurse", self.ue)
        for command in ("Remove-Item Intermediate, Source -Recurse", "rm -rf Intermediate Source",
                        "Remove-Item Plugins/Foo/Intermediate -Recurse", "Remove-Item Saved -Recurse",
                        "Remove-Item Intermediate/* -Recurse", "Remove-Item ../Intermediate -Recurse",
                        "Remove-Item $dir -Recurse", "Remove-Item -Recurse"):
            with self.subTest(command=command):
                self.assertFlagged(command, self.ue)

    # Review regressions (2026-10-15).
    def test_common_parameters_and_redirects_do_not_break_the_allowlist(self):
        for command in ("Remove-Item -Path Intermediate -Recurse -Force -ErrorAction SilentlyContinue",
                        "Remove-Item Intermediate -Recurse -ea 0", "Remove-Item Intermediate -Recurse 2>$null",
                        "Remove-Item Intermediate -Recurse *>$null", "rd /s /q Binaries 2>&1",
                        "Remove-Item Intermediate -Recurse > out.txt"):
            with self.subTest(command=command):
                self.assertClean(command, self.ue)

    def test_cd_in_the_same_command_voids_the_allowlist(self):
        for command in ("Set-Location C:/; Remove-Item Binaries -Recurse -Force", "cd ~ && rm -rf Library",
                        "sl .. ; Remove-Item Intermediate -Recurse"):
            with self.subTest(command=command):
                cwd = self.unity if "Library" in command else self.ue
                self.assertFlagged(command, cwd)


class SensitivePathTuning(unittest.TestCase):
    PATHS = ["C:/Users/me/.ssh/id_rsa", "C:/proj/certs/server.pem", "C:/proj/sign/release.keystore",
             "C:/proj/sign/upload.jks", "C:/proj/AuthKey_ABC.p8", "C:/Users/me/.netrc",
             "C:/proj/keys/private.key", "C:/proj/.env.local", "C:/Users/me/.aws/credentials",
             "C:/proj/sign/dist.p12", "C:/proj/sign/dist.pfx", "C:/proj/sign/App.mobileprovision",
             "C:/Users/me/.pgpass", "C:/Users/me/_netrc"]
    COMMANDS = [("PowerShell", "Get-Content C:/Users/me/.ssh/id_ed25519"), ("PowerShell", "type C:/proj/cert.pfx"),
                ("Bash", "cat ~/.ssh/id_rsa"), ("PowerShell", "Get-Content .env")]
    BENIGN_READS = ["C:/proj/Config/DefaultEngine.ini", "C:/proj/Source/Net/KeyboardInput.cpp",
                    "C:/proj/Docs/env-setup.md", "C:/proj/Source/Crypto/KeyManager.h",
                    "C:/proj/Plugins/Inventory/Inventory.uplugin", "C:/Users/me/.ssh_notes.md",
                    "C:/proj/Source/Crypto/PemParser.cpp", "C:/proj/Source/KeyStore.h"]

    def setUp(self):
        self.patterns = secret_scan._load_patterns()

    def test_sensitive_paths_are_blocked_for_writes_and_reads(self):
        for path in self.PATHS:
            with self.subTest(path=path):
                self.assertIsNotNone(secret_scan._scan("Write", {"file_path": path, "content": "x"},
                                                       self.patterns))
                self.assertTrue(_read_denied(path), f"no Read deny for {path}")

    def test_sensitive_paths_in_shell_arguments_are_blocked(self):
        for tool, command in self.COMMANDS:
            with self.subTest(command=command):
                self.assertIsNotNone(secret_scan._scan(tool, {"command": command}, self.patterns))

    def test_ordinary_sources_are_not_blocked(self):
        for path in self.BENIGN_READS:
            with self.subTest(path=path):
                self.assertIsNone(secret_scan._scan("Write", {"file_path": path, "content": "x"},
                                                    self.patterns))
                self.assertFalse(_read_denied(path), f"Read deny hit {path}")

    def test_powershell_property_access_is_not_a_key_file(self):
        for command in ("$h.GetEnumerator() | % { $_.Key }", "$entry.Key", "Write-Output $pair.Key)",
                        "[System.Environment]::GetEnvironmentVariable('X')", "ssh-keygen -l -f id_rsa.pub"):
            with self.subTest(command=command):
                self.assertIsNone(secret_scan._scan("PowerShell", {"command": command}, self.patterns))


class BenignTuning(_Base):
    CASES = [
        "git status", 'git commit -m "fix: crash in UMG"', "git push origin feature/inv",
        "Remove-Item Source/Foo.cpp", "Get-ChildItem -Recurse -Filter *.h",
        '& "C:/UE/Engine/Build/BatchFiles/Build.bat" SynthoriaEditor Win64 Development',
        "rm build.log", "Select-String -Path Source -Pattern UPROPERTY -Recurse",
        "git log --oneline -n 20", "dotnet test --no-build", "grep -rn 'no-verify' docs",
        "Copy-Item Content -Destination Backup -Recurse", "git commit -m 'docs: explain --no-verify policy'",
    ]

    def test_benign_commands_pass_both_hooks(self):
        patterns = secret_scan._load_patterns()
        for command in self.CASES:
            with self.subTest(command=command):
                self.assertClean(command)
                for tool in ("Bash", "PowerShell"):
                    self.assertIsNone(secret_scan._scan(tool, {"command": command}, patterns))


class EccDestructivePorts(_Base):
    """Adapted from ECC tests/lib/powershell-destructive-command.test.js (b92f181)."""

    def test_remove_item_forms(self):
        self.assertEqual(shell_guard.classify("Remove-Item -Recurse C:/tmp/demo"), ["remove.recurse"])
        self.assertEqual(shell_guard.classify("REMOVE-ITEM -Rec -Fo C:/tmp/demo"), ["remove.recurse"])
        self.assertEqual(shell_guard.classify("Remove-Item \u2014Recurse C:/tmp/demo"), ["remove.recurse"])
        self.assertEqual(shell_guard.classify("Rem`ove-Item -Rec`urse C:/tmp/demo"), ["remove.recurse"])
        for alias in ("ri", "rm", "rmdir", "rd", "del", "erase"):
            with self.subTest(alias=alias):
                self.assertEqual(shell_guard.classify(f"{alias} -Recurse C:/tmp/demo"), ["remove.recurse"])
        self.assertEqual(shell_guard.classify("Remove-Item C:/build/*"), ["remove.wildcard"])
        self.assertEqual(shell_guard.classify('Remove-Item "C:/build/file?.tmp"'), ["remove.wildcard"])
        self.assertEqual(shell_guard.classify("Remove-Item @deleteParams"), ["remove.splat"])
        self.assertClean("Remove-Item -LiteralPath 'C:/build/[x]*.txt'")
        self.assertClean("Remove-Item -Recurse:$false C:/tmp/demo")

    def test_destructive_cmdlets_and_dotnet(self):
        self.assertEqual(shell_guard.classify("Clear-Content C:/tmp/log.txt"), ["clear-content"])
        self.assertEqual(shell_guard.classify("Clear-Disk -Number 2 -RemoveData -Confirm:$false"), ["clear-disk"])
        self.assertEqual(shell_guard.classify("Format-Volume -DriveLetter D -Force"), ["format-volume"])
        self.assertEqual(shell_guard.classify("[System.IO.Directory]::Delete('C:/tmp/demo', $true)"),
                         ["dotnet.directory-delete"])
        self.assertEqual(shell_guard.classify("[IO.File]::Delete('C:/tmp/demo.txt')"), ["dotnet.file-delete"])
        self.assertEqual(shell_guard.classify("[IO.Fi`le]::Delete('C:/tmp/demo.txt')"), ["dotnet.file-delete"])
        self.assertClean("Write-Output \"[IO.File]::Delete('C:/tmp/demo.txt')\"")

    def test_cmd_recursive_delete(self):
        for command in ("cmd /c rd /s /q C:/tmp/demo", "cmd.exe /c del /s /q C:/tmp/demo/*",
                        'cmd /c "rd /s /q C:/tmp/demo"', "cmd /c @rd /s /q C:/tmp/demo",
                        "cmd /c --% rd /s /q C:/tmp/demo", "cmd /c if exist C:/tmp/demo rd /s /q C:/tmp/demo",
                        'cmd /c "(rd /s /q C:/tmp/demo)"', "cmd /c call rd /s /q C:/tmp/demo"):
            with self.subTest(command=command):
                self.assertIn("cmd.recursive-delete", shell_guard.classify(command))
        for command in ("cmd /c del C:/tmp/notes.txt", "cmd /c echo rd /s /q C:/tmp/demo",
                        'cmd /c "echo safe ^& rd /s /q C:/tmp/demo"'):
            with self.subTest(command=command):
                self.assertClean(command)

    def test_pipeline_and_nested_execution(self):
        self.assertEqual(shell_guard.classify("Get-ChildItem C:/tmp -Recurse | Remove-Item"),
                         ["remove.pipeline-recurse"])
        self.assertClean("Get-ChildItem C:/tmp -Recurse | Measure-Object")
        for command in ("1 | foreach { Remove-Item -Recurse C:/tmp/demo }",
                        "Invoke-Expression 'Remove-Item -Recurse C:/tmp/demo'",
                        'pwsh -Command:"Remove-Item -Recurse C:/tmp/demo"',
                        "Start-Process cmd -ArgumentList '/c rd /s /q C:/tmp/demo'",
                        "Write-Output $(Remove-Item -Recurse C:/tmp/demo)",
                        'Write-Output "$(Remove-Item -Recurse C:/tmp/demo)"',
                        "Remove-Item `\r\n-Recurse C:/tmp/demo"):
            with self.subTest(command=command):
                self.assertFlagged(command)
        payload = base64.b64encode("Remove-Item -Recurse C:/tmp/demo".encode("utf-16-le")).decode()
        self.assertFlagged(f"pwsh -EncodedCommand {payload}")
        self.assertIn("dynamic-execution", shell_guard.classify("Invoke-Expression $runtimeValue"))
        self.assertIn("dynamic-execution", shell_guard.classify("pwsh -Command $runtimeValue"))
        self.assertClean("pwsh -EncodedCommand %%%not-base64%%%")

    def test_comments_and_literals_are_not_executed(self):
        for command in ("Write-Output safe # ; Remove-Item -Recurse C:/tmp/demo",
                        "# [IO.File]::Delete('C:/tmp/demo')", "Write-Output 'Remove-Item -Recurse C:/tmp/demo'",
                        "Write-Output '$(Remove-Item -Recurse C:/tmp/demo)'", "Get-Date", "Get-ChildItem C:/tmp",
                        "Remove-Item C:/tmp/notes.txt", "<# Remove-Item -Recurse C:/tmp/demo #> Get-Date"):
            with self.subTest(command=command):
                self.assertClean(command)

    def test_depth_limit_reports_instead_of_recursing_forever(self):
        self.assertIn("scan-depth-exceeded", shell_guard.classify("(" * 40 + "Get-Date" + ")" * 40))


class EccGitBypassPorts(_Base):
    """Adapted from ECC tests/hooks/block-no-verify.test.js (b92f181)."""

    def test_bypass_forms(self):
        for command in ('git commit --no-verify -m "msg"', "echo $(echo $(git push --no-verify))",
                        "(git commit -m safe; git push --no-verify)", "echo safe # git commit -m safe\ngit push --no-verify",
                        "git commit --no-veri", "env -u HOME git push --no-verify", "sudo -u git git push --no-verify",
                        "git --config-env=core.hooksPath=HP commit -m x", "git --config-env core.hooksPath=HP commit -m x",
                        "git -cinclude.path=/tmp/evil.conf commit -m x", "git -c INCLUDE.PATH=/tmp/evil.conf commit -m x",
                        "git -c includeIf.gitdir:**/.path=/tmp/evil.conf commit -m x",
                        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m x",
                        "export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null; git commit",
                        "git commit -an -m x", '"git" commit --no-verify', "C:/Git/cmd/git.exe push --no-verify",
                        "git -C repo commit --no-verify"):
            with self.subTest(command=command):
                self.assertFlagged(command)

    def test_data_and_values_are_not_bypasses(self):
        for command in ('git commit -m "hello"', "git commit -m --no-verify", "git commit -Skeyn -m x",
                        "git commit -- --no-verify", "echo safe # git push --no-verify",
                        "git commit -m safe # --no-verify", "git -c user.name=ECC commit -m x",
                        "git -c include.path=/tmp/evil.conf status", "git --config-env=core.hooksPath=HP status",
                        "git commit -uno -m x", "command -v git push --no-verify", "git push -n origin main",
                        "git merge -n feature", "git commit --message='skip --no-verify' -a"):
            with self.subTest(command=command):
                self.assertClean(command)


class ReviewRegressions(_Base):
    """Inputs from the independent review of 2026-10-15 (code-reviewer, REQUEST CHANGES)."""

    def test_assignment_does_not_hide_the_command(self):
        for command in ("$null = Remove-Item src -Recurse -Force", "$r = rm -rf build",
                        "$out = git commit -n -m x", "$x = git push --no-verify"):
            with self.subTest(command=command):
                self.assertFlagged(command)
        self.assertClean("$p = 'Source'")

    def test_quoted_and_here_string_text_is_data(self):
        self.assertEqual(shell_guard.classify("git commit -m 'docs: explain `rm -rf build` usage'", shell="bash"), [])
        self.assertEqual(shell_guard.classify('git commit -m "docs: `Remove-Item -Recurse` usage"',
                                              shell="powershell"), [])
        self.assertIn("remove.recurse", shell_guard.classify("echo `rm -rf build`", shell="bash"))
        self.assertIn("remove.recurse", shell_guard.classify('echo "`rm -rf build`"', shell="bash"))
        for body in ("feat: don't block\n\ngit commit --no-verify is now flagged",
                     "feat: don't block\n\nRemove-Item src -Recurse is flagged"):
            with self.subTest(body=body):
                self.assertEqual(shell_guard.classify("git commit -m @'\n" + body + "\n'@", shell="powershell"), [])
        self.assertIn("remove.recurse",
                      shell_guard.classify('Write-Output @"\n$(Remove-Item src -Recurse)\n"@', shell="powershell"))

    def test_more_destructive_forms(self):
        for command in ("cmd /c rd /s/q build", "gci src -Recurse -File | % { Remove-Item $_ }",
                        "timeout 10 rm -rf build", "wsl rm -rf build", "wsl -d Ubuntu rm -rf build"):
            with self.subTest(command=command):
                self.assertFlagged(command)
        self.assertIn("remove.recurse", shell_guard.classify("echo it\\'s; rm -rf build", shell="bash"))
        # Re-review (2026-10-15): wrapper options and nested-shell syntax.
        for command in ("timeout -s KILL 10 rm -rf build", "timeout --signal=KILL 10 rm -rf build"):
            with self.subTest(command=command):
                self.assertFlagged(command)
        self.assertIn("remove.recurse", shell_guard.classify("bash -c 'echo `rm -rf build`'", shell="powershell"))
        self.assertEqual(shell_guard.classify("pwsh -c 'Write-Output `$x'", shell="bash"), [])

    def test_unbalanced_subexpressions_stay_fast(self):
        import time
        start = time.perf_counter()
        shell_guard.classify('"' + "$(" * 3000 + '"')
        self.assertLess(time.perf_counter() - start, 0.15)


class ReviewSecretScanRegressions(unittest.TestCase):
    BENIGN = ['py -3 -c "k = obj.key; print(k)"', 'node -e "x = cfg.key"', "print(cfg['a'].key)",
              "Sort-Object -Property Value.Key", "gh api repos/o/r/keys --jq '.[].key'",
              'Add-Content .gitignore "*.pem"', "echo '*.keystore' >> .gitignore",
              "Get-ChildItem -Recurse -Filter *.keystore", "git ls-files '*.key'",
              "RunUAT.bat BuildCookRun -platform=IOS -mobileprovision=Game_Dev.mobileprovision",
              "signtool sign /f cert.pfx /p x Game.exe", "keytool -list -keystore debug.keystore",
              "cat config.json | jq .key"]

    def test_code_globs_and_signing_commands_are_not_blocked(self):
        patterns = secret_scan._load_patterns()
        for command in self.BENIGN:
            for tool in ("Bash", "PowerShell"):
                with self.subTest(command=command, tool=tool):
                    self.assertIsNone(secret_scan._scan(tool, {"command": command}, patterns))

    def test_reading_key_material_is_still_blocked(self):
        patterns = secret_scan._load_patterns()
        for command in ("head -n 3 certs/server.pem", "Get-Content C:/proj/sign/upload.jks | Out-Null",
                        "cp ~/.aws/credentials /tmp/x", "base64 id_rsa", "type _netrc",
                        "Format-Hex C:/proj/sign/release.keystore", "certutil -dump cert.pfx"):
            with self.subTest(command=command):
                self.assertIsNotNone(secret_scan._scan("PowerShell", {"command": command}, patterns))


class HandlerContract(unittest.TestCase):
    def _run(self, mode, command, tool="PowerShell"):
        import os
        import subprocess
        env = dict(os.environ, CLAUDE_SHELL_GUARD_MODE=mode)
        handler = Path(__file__).resolve().parents[1] / "handlers" / "shell_guard.py"
        return subprocess.run([sys.executable, str(handler)], capture_output=True, text=True, env=env,
                              input=json.dumps({"tool_name": tool, "tool_input": {"command": command},
                                                "cwd": tempfile.gettempdir()}))

    def test_modes(self):
        bad = "Remove-Item src -Recurse"
        enforce = self._run("enforce", bad)
        self.assertEqual(enforce.returncode, 2)
        self.assertIn("[shell_guard:block] remove.recurse", enforce.stderr)
        dry = self._run("dryrun", bad)
        self.assertEqual(dry.returncode, 0)
        self.assertIn("[WARN] [shell_guard:warn:dryrun]", dry.stderr)
        self.assertEqual(self._run("off", bad).returncode, 0)
        clean = self._run("enforce", "git status")
        self.assertEqual((clean.returncode, clean.stderr), (0, ""))
        other = self._run("enforce", bad, tool="Write")
        self.assertEqual(other.returncode, 0)

    def test_settings_template_wires_shell_guard_in_dryrun(self):
        template = json.loads(_TEMPLATE.read_text(encoding="utf-8"))
        entries = [e for e in template["hooks"]["PreToolUse"]
                   if e["hooks"][0]["command"].endswith("/shell_guard.cmd")]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["matcher"], "Bash|PowerShell")
        self.assertEqual(template["env"]["CLAUDE_SHELL_GUARD_MODE"], "dryrun")
        # Decision 2 (ADR-0024): the deny globs stay until shell_guard is promoted to enforce.
        self.assertIn("Bash(rm -rf *)", template["permissions"]["deny"])
        self.assertIn("PowerShell(Remove-Item *-Recurse*)", template["permissions"]["deny"])


if __name__ == "__main__":
    unittest.main()
