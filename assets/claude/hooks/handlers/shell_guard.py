"""ADR-0024 shell_guard PreToolUse hook.

Flags destructive shell commands and git hook bypass in Bash / PowerShell tool
calls. Mode from ``CLAUDE_SHELL_GUARD_MODE``: ``off`` | ``dryrun`` (default) |
``enforce``. This is a best-effort lexical check, not containment: anything a
shell can compute at run time (variables, generated strings, interpreters such
as ``python -c``) is out of reach. Sandbox is absent on Windows (ADR-0024).

Rule taxonomy and git option parsing adapted from affaan-m/ECC (MIT License,
Copyright (c) 2026 Affaan Mustafa), commit b92f181:
  scripts/lib/powershell-destructive-command.js  (RULE_IDS, delete-command aliases)
  scripts/hooks/block-no-verify.js               (hook-redirect keys, commit -n clusters)
It is a reduced stdlib-only reimplementation, not a line port. Not ported:
alias/function definition tracking, static string assembly, here-strings piped
to ``pwsh -Command -``. Deliberate deviation: a bare ``-Force`` is not flagged.
Added beyond ECC: ``robocopy /MIR``, ``find -delete``, git config writes and
``HUSKY=0``, and the engine cleanup allowlist (ADR-0024 decision 2).
"""
from __future__ import annotations

import base64
import os
import re
import sys
from pathlib import Path
from typing import NamedTuple, Optional

_HANDLER_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _HANDLER_DIR.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

from lib.common import (  # noqa: E402  (sys.path insert above)
    exit_allow,
    exit_block,
    exit_warn,
    get_env_override,
    log_event,
    read_hook_input,
    run_handler,
)

_HOOK_NAME = "shell_guard"
_EVENT = "PreToolUse"
_TARGET_TOOLS = {"Bash", "PowerShell"}
_MAX_DEPTH = 12

_DELETE_COMMANDS = {"remove-item", "remove-itemproperty", "rp", "ri", "rm", "rmdir", "rd", "del", "erase"}
_CMD_DELETE_COMMANDS = {"rd", "rmdir", "del", "erase"}
_PWSH = {"powershell", "pwsh"}
_POSIX_SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
_REMOVE_VALUE_PARAMS = ("filter", "include", "exclude", "credential", "stream")
# PowerShell common parameters that take a value, with their aliases.
_COMMON_VALUE_PARAMS = {"erroraction", "ea", "warningaction", "wa", "informationaction", "infa",
                        "errorvariable", "ev", "warningvariable", "wv", "informationvariable", "iv",
                        "outvariable", "ov", "outbuffer", "ob", "pipelinevariable", "pv"}
_CD_COMMANDS = {"cd", "chdir", "set-location", "sl", "pushd", "push-location"}
_REDIRECT_RE = re.compile(r"^(?:\d|\*|&)?>>?")
_CD_RE = re.compile(r"(?i)(?:^|[;&|\n({]\s*)(?:cd|chdir|set-location|sl|pushd|push-location)(?=\s|$)")
_GROUP_DELETE_RE = re.compile(r"(?i)(?:^|[\s;{|(])(?:remove-item|ri|rm|rmdir|rd|del|erase)(?=\s|$)")
_START_PROCESS_VALUE_PARAMS = ("credential", "environment", "redirectstandarderror", "redirectstandardinput",
                               "redirectstandardoutput", "verb", "windowstyle", "workingdirectory")
# Wrapper commands that run their argument as a command, with the options that take a value.
_WRAPPERS = {
    "sudo": {"-u", "-g", "-h", "-p", "-c", "-C", "-D", "-r", "-t", "-U"},
    "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
    "xargs": {"-I", "-i", "-n", "-P", "-L", "-l", "-d", "-E", "-e", "-s", "-a"},
    "exec": {"-a"},
    "nice": {"-n"},
    "wsl": {"-d", "--distribution", "-u", "--user", "--cd"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "nohup": set(), "command": set(), "time": set(),
}
_POSITIONAL_WRAPPERS = {"timeout": 1}  # wrapper -> positional args before the command
_EXPORTERS = {"export", "set", "declare", "typeset"}

# Engine cleanup allowlist: exact top-level paths, active only at a marked project root.
_UE_CLEANUP = {"intermediate", "binaries", "deriveddatacache", "saved/logs"}
_UNITY_CLEANUP = {"library", "temp", "obj", "bin"}
_ALLOWLISTABLE = {"remove.recurse", "cmd.recursive-delete"}

_GIT_PROTECTED = {"commit", "push", "merge", "cherry-pick", "rebase", "am"}
_GIT_GLOBAL_VALUES = {"-c", "-C", "--config-env", "--work-tree", "--git-dir", "--namespace", "--super-prefix"}
_COMMIT_VALUE_OPTS = {"-m", "--message", "-F", "--file", "-C", "--reuse-message", "-c", "--reedit-message",
                      "--author", "--date", "--template", "--fixup", "--squash", "--pathspec-from-file"}
_OTHER_VALUE_OPTS = {"-m", "--message", "-F", "--file", "-s", "--strategy", "-X", "--strategy-option",
                     "-o", "--push-option", "--repo", "--onto", "--exec", "-x", "--receive-pack"}
_CONFIG_VALUE_OPTS = {"-f", "--file", "--blob", "--type", "--default", "--comment", "-t"}
_CONFIG_READ_OR_REMOVE = {"--get", "--get-all", "--get-regexp", "--get-urlmatch", "--unset", "--unset-all",
                          "-l", "--list", "--remove-section", "--rename-section", "get", "unset", "list",
                          "remove-section", "rename-section"}

_ASSIGN_RE = re.compile(r"^\$?(?:env:)?([A-Za-z_]\w*)=(.*)$", re.S)
_DOTNET_DIR_RE = re.compile(r"\[\s*(?:system\.)?io\.directory\s*\]\s*::\s*delete\s*\(", re.I)
_DOTNET_FILE_RE = re.compile(r"\[\s*(?:system\.)?io\.file\s*\]\s*::\s*delete\s*\(", re.I)
_HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_]\w*)\1")
_EXECUTES_STDIN_RE = re.compile(r"^\s*(?:bash|sh|zsh|dash|ksh|pwsh|powershell)\b|\|\s*(?:bash|sh|zsh|dash|ksh)\b", re.I)
_PUNCT = str.maketrans({"–": "-", "—": "-", "―": "-", "‘": "'", "’": "'",
                        "‚": "'", "‛": "'", "“": '"', "”": '"', "„": '"'})


class Tok(NamedTuple):
    value: str    # quotes removed; bracket groups kept verbatim
    quoted: bool  # the word starts with a quoted part (so it is not a parameter or variable)


class _State:
    def __init__(self, cwd: Optional[Path], shell: Optional[str]):
        self.findings: set[str] = set()
        self.cwd = cwd
        self.shell = shell
        self.cwd_changed = False  # a cd/Set-Location earlier in the command voids the allowlist
        self.env: dict[str, str] = {}
        self._cleanup_names: Optional[set[str]] = None

    def cleanup_names(self) -> set[str]:
        if self._cleanup_names is None:
            names: set[str] = set()
            try:
                if self.cwd is not None and self.cwd.is_dir():
                    if any(self.cwd.glob("*.uproject")):
                        names |= _UE_CLEANUP
                    if (self.cwd / "ProjectSettings" / "ProjectVersion.txt").is_file():
                        names |= _UNITY_CLEANUP
            except OSError:
                pass
            self._cleanup_names = names
        return self._cleanup_names


# --------------------------------------------------------------------------- lexing

def _match_close(text: str, i: int) -> int:
    """Index of the bracket closing ``text[i]`` (quote-aware), or -1."""
    open_ch = text[i]
    close_ch = ")" if open_ch == "(" else "}"
    depth, j, n = 0, i, len(text)
    while j < n:
        c = text[j]
        if c == "`":
            j += 2
            continue
        if c in "'\"":
            k = text.find(c, j + 1)
            if k < 0:
                return -1
            j = k + 1
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    return -1


def _strip_heredocs(text: str) -> str:
    """Blank heredoc bodies fed to a non-shell command: they are data, not commands."""
    lines = text.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        m = _HEREDOC_RE.search(line)
        i += 1
        if not m or _EXECUTES_STDIN_RE.search(line):
            continue
        delim = m.group(2)
        while i < len(lines) and lines[i].strip() != delim:
            out.append("")
            i += 1
    return "\n".join(out)


def _subexpressions(body: str) -> list[str]:
    """``$( ... )`` bodies inside an expandable (double-quoted) string."""
    out, j = [], body.find("$(")
    while j >= 0:
        if j > 0 and body[j - 1] == "`":
            j = body.find("$(", j + 2)
            continue
        k = _match_close(body, j + 1)
        if k < 0:
            break
        out.append(body[j + 2:k])
        j = body.find("$(", k + 1)
    return out


def _lex(text: str, powershell: bool = False):
    """Split into statements -> pipeline segments -> tokens; collect bracket/subexpr bodies."""
    statements: list[list[list[Tok]]] = []
    groups: list[str] = []
    pipeline: list[list[Tok]] = []
    seg: list[Tok] = []
    buf: list[str] = []
    quoted = False
    has = False

    def end_tok():
        nonlocal buf, quoted, has
        if has:
            seg.append(Tok("".join(buf), quoted))
        buf, quoted, has = [], False, False

    def end_seg():
        nonlocal seg
        end_tok()
        if seg:
            pipeline.append(seg)
        seg = []

    def end_stmt():
        nonlocal pipeline
        end_seg()
        if pipeline:
            statements.append(pipeline)
        pipeline = []

    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "`":  # PowerShell escape: next character is literal
            if i + 1 < n:
                buf.append(text[i + 1])
                has = True
            i += 2
            continue
        if c == "\\" and i + 1 < n and text[i + 1] in (";|&" if powershell else ";|&'\""):  # POSIX escape
            buf.append(text[i + 1])
            has = True
            i += 2
            continue
        if c == "@" and not has and i + 1 < n and text[i + 1] in "'\"" and re.match(r"[ \t]*\r?\n", text[i + 2:]):
            # PowerShell here-string: literal until a line starting with the closing quote + '@'.
            q = text[i + 1]
            end = text.find("\n" + q + "@", i + 2)
            body = text[i + 2:] if end < 0 else text[i + 2:end]
            if q == '"':
                groups.extend(_subexpressions(body))
            buf.append(body)
            quoted = has = True
            i = n if end < 0 else end + 3
            continue
        if c in " \t\r":
            end_tok()
            i += 1
            continue
        if c in "\n;":
            end_stmt()
            i += 1
            continue
        if c == "#" and not has:
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "<" and text.startswith("<#", i) and not has:
            j = text.find("#>", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "|":
            if text.startswith("||", i):
                end_stmt()
                i += 2
            else:
                end_seg()
                i += 1
            continue
        if c == "&" and ((i > 0 and text[i - 1] == ">") or text.startswith("&>", i)):
            buf.append(c)  # redirection such as 2>&1 or &>file
            has = True
            i += 1
            continue
        if c == "&":
            if text.startswith("&&", i):
                end_stmt()
                i += 2
                continue
            end_tok()
            if seg:  # POSIX background separator; a leading & is PowerShell's call operator
                end_stmt()
            i += 1
            continue
        if c == "'":
            j, part = i + 1, []
            while j < n:
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        part.append("'")
                        j += 2
                        continue
                    break
                part.append(text[j])
                j += 1
            buf.append("".join(part))
            quoted = quoted or not has
            has = True
            i = j + 1
            continue
        if c == '"':
            j, part = i + 1, []
            subexpr_ok = True  # one unbalanced $( ends the search, keeping this linear
            while j < n and text[j] != '"':
                ch = text[j]
                if ch in "`\\" and j + 1 < n and text[j + 1] in '"$`':
                    part.append(text[j + 1])
                    j += 2
                    continue
                if subexpr_ok and ch == "$" and j + 1 < n and text[j + 1] == "(":
                    k = _match_close(text, j + 1)
                    subexpr_ok = k > 0
                    if k > 0:
                        groups.append(text[j + 2:k])
                        part.append(text[j:k + 1])
                        j = k + 1
                        continue
                part.append(ch)
                j += 1
            buf.append("".join(part))
            quoted = quoted or not has
            has = True
            i = j + 1
            continue
        if c in "({":
            k = _match_close(text, i)
            end = n if k < 0 else k + 1
            groups.append(text[i + 1:(n if k < 0 else k)])
            buf.append(text[i:end])
            has = True
            i = end
            continue
        if c in ")}":
            i += 1
            continue
        buf.append(c)
        has = True
        i += 1
    end_stmt()
    return statements, groups


# --------------------------------------------------------------------------- helpers

def _cmd_name(word: str) -> str:
    name = re.split(r"[\\/]", word)[-1].lower().lstrip("@")
    for ext in (".exe", ".cmd", ".bat", ".com"):
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def _param(tok: Tok):
    """``-Name:value`` -> ("name", "value", True); non-parameters -> None."""
    v = tok.value
    if tok.quoted or len(v) < 2 or v[0] != "-" or v.startswith("--"):
        return None
    name, sep, inline = v[1:].partition(":")
    return name.lower(), inline, bool(sep)


def _is_prefix(short: str, full: str, minimum: int = 1) -> bool:
    return len(short) >= minimum and full.startswith(short)


def _join(toks) -> str:
    return " ".join(t.value for t in toks)


def _b64_utf16(value: str) -> Optional[str]:
    try:
        return base64.b64decode(value, validate=True).decode("utf-16-le")
    except Exception:
        return None


def _is_hook_key(key: str) -> bool:
    key = key.strip().lower()
    return key in ("core.hookspath", "include.path") or bool(re.fullmatch(r"includeif\..*\.path", key))


def _is_hook_setting(setting: str) -> bool:
    return _is_hook_key(setting.split("=", 1)[0])


def _env_hook_override(env: dict) -> bool:
    for key, value in env.items():
        if re.fullmatch(r"GIT_CONFIG_KEY_\d+", key) and _is_hook_key(value):
            return True
        if key == "GIT_CONFIG_PARAMETERS" and re.search(r"(?i)core\.hookspath|include\.path|includeif\.", value):
            return True
    return False


# --------------------------------------------------------------------------- rules

def _remove(args, st: _State) -> tuple[set[str], bool]:
    found: set[str] = set()
    targets: list[str] = []
    literal = any((p := _param(a)) and _is_prefix(p[0], "literalpath", 2) for a in args)
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        v = a.value
        if not a.quoted and _REDIRECT_RE.match(v):  # 2>$null, *>$null, 2>&1, or a bare > before its target
            skip = bool(re.fullmatch(r"(?:\d|\*|&)?>>?", v))
            continue
        if not a.quoted and v.startswith("@") and not v.startswith("@("):
            found.add("remove.splat")
            continue
        if not a.quoted and v.startswith("--"):
            if v == "--recursive":
                found.add("remove.recurse")
            continue
        p = _param(a)
        if p:
            name, inline, _ = p
            if inline.lower() == "$false":
                continue
            if _is_prefix(name, "recurse") or (re.fullmatch(r"[rfidv]+", name) and "r" in name):
                found.add("remove.recurse")
            elif name in _COMMON_VALUE_PARAMS or (
                    len(name) >= 3 and any(full.startswith(name) for full in _REMOVE_VALUE_PARAMS)):
                skip = not inline
            continue
        if not a.quoted and re.fullmatch(r"(?:/[A-Za-z])+", v):  # cmd switches, also clustered: /s/q
            if "/s" in v.lower():
                found.add("cmd.recursive-delete")
            continue
        for part in v.split(","):
            if part:
                targets.append(part)
                if not literal and ("*" in part or "?" in part):
                    found.add("remove.wildcard")
    recursive = bool(found & _ALLOWLISTABLE)
    if found and found <= _ALLOWLISTABLE and targets and all(_allowlisted(t, st) for t in targets):
        return set(), recursive
    return found, recursive


def _allowlisted(target: str, st: _State) -> bool:
    names = st.cleanup_names()
    if not names or st.cwd is None or st.cwd_changed or target.startswith(("$", "~", "(")):
        return False
    try:
        full = os.path.normpath(os.path.join(str(st.cwd), target))
        rel = os.path.relpath(full, str(st.cwd)).replace("\\", "/").lower()
    except ValueError:  # different drive
        return False
    return rel in names


def _scan_cmd(payload: str, depth: int, st: _State) -> None:
    for part in re.split(r"(?<!\^)(?:&&|\|\||&|\|)", payload):
        words = [w.strip("()\"").lstrip("@") for w in part.split()]
        words = [w for w in words if w and w != "--%"]
        if not words or words[0].lower() in ("echo", "rem", "set"):
            continue
        for i, w in enumerate(words):
            lw = _cmd_name(w)
            if w.lower() in _CMD_DELETE_COMMANDS:
                st.findings |= _remove([Tok(x, False) for x in words[i + 1:]], st)[0]
                break
            if lw in _PWSH or lw in ("cmd", "robocopy"):
                _scan(" ".join(words[i:]), depth + 1, st)
                break


def _payload(toks, depth: int, st: _State, shell: str) -> None:
    """Scan a command string handed to an interpreter (iex, pwsh -c, bash -c) in its own syntax."""
    if not toks or toks[0].value == "-":
        return  # stdin: not visible here
    if not toks[0].quoted and toks[0].value.startswith("$"):
        st.findings.add("dynamic-execution")
        return
    _scan_as(_join(toks), depth + 1, st, shell)


def _scan_as(text: str, depth: int, st: _State, shell: str) -> None:
    outer, st.shell = st.shell, shell
    try:
        _scan(text, depth, st)
    finally:
        st.shell = outer


def _pwsh(args, depth: int, st: _State) -> None:
    for i, a in enumerate(args):
        p = _param(a)
        if not p:
            continue
        name, inline, has_inline = p
        rest = ([Tok(inline, False)] if has_inline else []) + list(args[i + 1:])
        if name in ("c", "cwa", "commandwithargs") or _is_prefix(name, "command", 3):
            _payload(rest, depth, st, "powershell")
            return
        if name in ("e", "ec") or _is_prefix(name, "encodedcommand", 2):
            value = rest[0].value if rest else ""
            if value.startswith("$"):
                st.findings.add("dynamic-execution")
            elif (decoded := _b64_utf16(value)) is not None:
                _scan_as(decoded, depth + 1, st, "powershell")
            return
        if _is_prefix(name, "file", 1):
            return


def _posix_shell(args, depth: int, st: _State) -> None:
    for i, a in enumerate(args):
        if not a.quoted and re.fullmatch(r"-[a-z]*c[a-z]*", a.value):
            _payload(args[i + 1:i + 2], depth, st, "bash")
            return


def _start_process(args, depth: int, st: _State) -> None:
    file_tok, arglist, positional = None, [], []
    i = 0
    while i < len(args):
        a, p = args[i], _param(args[i])
        if p:
            name, inline, has_inline = p
            value = Tok(inline, False) if has_inline else (args[i + 1] if i + 1 < len(args) else None)
            step = 1 if has_inline else 2
            if name == "f" or _is_prefix(name, "filepath", 2):
                file_tok = value
            elif name == "args" or _is_prefix(name, "argumentlist", 2):
                arglist = [value] if value else []
            elif len(name) >= 2 and any(full.startswith(name) for full in _START_PROCESS_VALUE_PARAMS):
                pass
            else:
                step = 1
            i += step
            continue
        positional.append(a)
        i += 1
    if file_tok is None and positional:
        file_tok, positional = positional[0], positional[1:]
    if not arglist:
        arglist = positional
    if file_tok is None:
        return
    if arglist and not arglist[0].quoted and arglist[0].value.startswith("$"):
        st.findings.add("dynamic-execution")
        return
    _scan(_cmd_name(file_tok.value) + " " + _join(arglist).replace(",", " "), depth + 1, st)


def _git(args, env: dict, st: _State) -> None:
    override = _env_hook_override(env)
    i = 0
    while i < len(args):
        v = args[i].value
        if not v.startswith("-"):
            break
        if v == "--":
            i += 1
            break
        if v in ("-c", "--config-env"):
            override |= i + 1 < len(args) and _is_hook_setting(args[i + 1].value)
        elif v.startswith("--config-env="):
            override |= _is_hook_setting(v[len("--config-env="):])
        elif v.startswith("-c") and not v.startswith("--"):
            override |= _is_hook_setting(v[2:])
        i += 2 if v in _GIT_GLOBAL_VALUES else 1
    if i >= len(args):
        return
    sub, rest = args[i].value.lower(), args[i + 1:]
    if sub == "config":
        _git_config(rest, st)
        return
    if sub not in _GIT_PROTECTED:
        return
    if override:
        st.findings.add("git.hooks-path")
    if env.get("HUSKY") == "0":
        st.findings.add("git.husky-disabled")
    j = 0
    while j < len(rest):
        v = rest[j].value
        if v == "--":
            break
        if v.startswith("--no-v") and "--no-verify".startswith(v):
            st.findings.add("git.no-verify")
        elif sub == "commit":
            if _commit_no_verify_short(v):
                st.findings.add("git.no-verify")
            elif v in _COMMIT_VALUE_OPTS or _commit_short_consumes_next(v):
                j += 1
        elif v in _OTHER_VALUE_OPTS:
            j += 1
        j += 1


def _commit_no_verify_short(v: str) -> bool:
    if not v.startswith("-") or v.startswith("--") or v == "-":
        return False
    for ch in v[1:]:
        if ch == "n":
            return True
        if ch in "mFCctuS":  # value-taking options swallow the rest of the cluster
            return False
    return False


def _commit_short_consumes_next(v: str) -> bool:
    if not v.startswith("-") or v.startswith("--") or v == "-":
        return False
    for idx, ch in enumerate(v[1:]):
        if ch in "mFCct":
            return idx == len(v) - 2
        if ch in "uS":
            return False
    return False


def _git_config(rest, st: _State) -> None:
    positional, skip = [], False
    for a in rest:
        v = a.value
        if skip:
            skip = False
            continue
        if v.lower() in _CONFIG_READ_OR_REMOVE:
            return
        if v in _CONFIG_VALUE_OPTS:
            skip = True
            continue
        if v.startswith("-") or v.lower() == "set":
            continue
        positional.append(v)
    if len(positional) >= 2 and _is_hook_key(positional[0]):
        st.findings.add("git.hooks-path")


def _segment(seg, depth: int, st: _State) -> tuple[bool, bool]:
    """Classify one pipeline segment. Returns (is_delete, has_recurse_switch)."""
    toks = list(seg)
    env_local: dict[str, str] = {}
    persist = False
    while toks:
        t = toks[0]
        if not t.quoted and len(toks) >= 3 and toks[1].value == "=" and t.value.startswith("$"):
            m = _ASSIGN_RE.match(t.value + "=" + toks[2].value)
            if m:
                env_local[m.group(1).upper()] = m.group(2)
            toks = toks[2:]  # `$x = <command>` still runs the command on the right
            persist = True
            continue
        m = _ASSIGN_RE.match(t.value)
        if m:
            env_local[m.group(1).upper()] = m.group(2)
            toks.pop(0)
            continue
        name = _cmd_name(t.value)
        if name in _EXPORTERS and not t.quoted:
            toks.pop(0)
            persist = True
            while toks and toks[0].value.startswith("-"):
                toks.pop(0)
            continue
        if name in _WRAPPERS and not t.quoted:
            values = _WRAPPERS[name]
            toks.pop(0)
            while toks and toks[0].value.startswith("-") and not toks[0].quoted:
                flag = toks.pop(0).value
                if name == "command" and flag in ("-v", "-V"):
                    return False, False  # lookup, not execution
                if flag in values and toks:
                    toks.pop(0)
            toks = toks[_POSITIONAL_WRAPPERS.get(name, 0):]
            continue
        break
    if persist or not toks:
        st.env.update(env_local)
    if not toks:
        return False, False
    env = {**st.env, **env_local}
    head, args = toks[0], toks[1:]
    name = _cmd_name(head.value)
    has_recurse = any((p := _param(a)) and _is_prefix(p[0], "recurse") and p[1].lower() != "$false"
                      for a in args)
    if name in _DELETE_COMMANDS:
        found, _ = _remove(args, st)
        st.findings |= found
        return True, has_recurse
    if name in ("foreach-object", "foreach", "%") and any(
            a.value.startswith("{") and _GROUP_DELETE_RE.search(a.value) for a in args):
        return True, has_recurse  # `... | % { Remove-Item $_ }` deletes what the pipeline feeds it
    if name in ("clear-content", "clc"):
        st.findings.add("clear-content")
    elif name == "clear-disk":
        st.findings.add("clear-disk")
    elif name == "format-volume":
        st.findings.add("format-volume")
    elif name == "robocopy":
        if any(a.value.lower() in ("/mir", "/purge") for a in args):
            st.findings.add("robocopy.mirror")
    elif name == "find":
        for k, a in enumerate(args):
            if a.value == "-delete" or (a.value in ("-exec", "-execdir", "-ok", "-okdir") and k + 1 < len(args)
                                        and _cmd_name(args[k + 1].value) in _DELETE_COMMANDS | {"shred", "unlink"}):
                st.findings.add("find.delete")
                break
    elif name == "cmd":
        for k, a in enumerate(args):
            if a.value.lower() in ("/c", "/k"):
                _scan_cmd(_join(args[k + 1:]), depth, st)
                break
    elif name in _PWSH:
        _pwsh(args, depth, st)
    elif name in _POSIX_SHELLS:
        _posix_shell(args, depth, st)
    elif name in ("iex", "invoke-expression"):
        rest = [a for a in args if not ((p := _param(a)) and _is_prefix(p[0], "command"))]
        _payload(rest, depth, st, "powershell")
    elif name in ("start-process", "saps", "start"):
        _start_process(args, depth, st)
    elif name == "git":
        _git(args, env, st)
    return False, has_recurse


def _scan(text: str, depth: int, st: _State) -> None:
    if depth > _MAX_DEPTH:
        st.findings.add("scan-depth-exceeded")
        return
    text = re.sub(r"[`\\]\r?\n", " ", text.translate(_PUNCT))
    text = _strip_heredocs(text)
    powershell = st.shell == "powershell"
    if not powershell:
        # POSIX command substitution with backticks (not inside single quotes). PowerShell reads
        # backticks as escapes, so this is skipped there.
        for body in re.findall(r"`([^`]*)`", re.sub(r"'[^']*'", "''", text)):
            if " " in body.strip():
                _scan(body, depth + 1, st)
    statements, groups = _lex(text, powershell)
    for body in groups:
        _scan(body, depth + 1, st)
    for pipeline in statements:
        deletes, recursive = set(), set()
        for k, seg in enumerate(pipeline):
            for tok in seg:
                if not tok.quoted:
                    if _DOTNET_DIR_RE.search(tok.value):
                        st.findings.add("dotnet.directory-delete")
                    if _DOTNET_FILE_RE.search(tok.value):
                        st.findings.add("dotnet.file-delete")
            is_delete, has_recurse = _segment(seg, depth, st)
            if is_delete:
                deletes.add(k)
            if has_recurse:
                recursive.add(k)
        if len(pipeline) > 1 and deletes and (recursive - deletes):
            st.findings.add("remove.pipeline-recurse")


def classify(command: str, cwd=None, shell: Optional[str] = None) -> list[str]:
    """Return the sorted rule ids a shell command triggers ([] = clean).

    ``shell`` is "bash" or "powershell" (from the tool name); None reads backticks the bash way.
    Nested ``bash -c`` / ``pwsh -c`` / ``iex`` payloads switch to their own reading.
    """
    command = command if isinstance(command, str) else ""
    st = _State(Path(cwd) if cwd else None, shell)
    st.cwd_changed = bool(_CD_RE.search(command))
    _scan(command, 0, st)
    return sorted(st.findings)


def main() -> None:
    payload = read_hook_input()
    mode = get_env_override("CLAUDE_SHELL_GUARD_MODE", "dryrun")
    if mode == "off":
        exit_allow()
    tool_name = payload.get("tool_name")
    if tool_name not in _TARGET_TOOLS:
        exit_allow()
    command = (payload.get("tool_input") or {}).get("command", "") or ""
    findings = classify(command, payload.get("cwd"), "powershell" if tool_name == "PowerShell" else "bash")
    if not findings:
        exit_allow()
    fields = {"event": _EVENT, "tool_name": tool_name, "rules": findings}
    if mode == "enforce":
        log_event(_HOOK_NAME, decision="block", **fields)
        exit_block(f"[shell_guard:block] {', '.join(findings)}")
    log_event(_HOOK_NAME, decision="warn", **fields)
    exit_warn(f"[shell_guard:warn:dryrun] {', '.join(findings)}")


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
