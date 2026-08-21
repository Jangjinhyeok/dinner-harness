"""ADR-0005 scope-whitelist PreToolUse hook.

Reads a Claude Code hook payload from stdin. For ``Edit`` / ``Write``
calls, normalises ``file_path`` to an absolute POSIX path and runs two
policy layers:

  1. always-block: for the structured file-edit tools in ``_TARGET_TOOLS``
     (``Edit``, ``Write``, and ``apply_patch``), paths matching
     ``rules/scope_protect.json`` are blocked unconditionally inside
     ``~/.claude/`` (dryrun-exempt, immediate enforce). Mode ``off`` is the only
     escape. Writes through ``Bash`` or PowerShell are intentionally outside
     this layer. Like ``builder_guard.py``, it is a workflow guard, not a
     sandbox; containment belongs to the sandbox.
  2. scope codeblock: paths must match an entry in the first
     ``` ```scope ``` codeblock of the handoff named by
     ``CLAUDE_SCOPE_HANDOFF_NAME`` (default ``HANDOFF.md``). An absent
     or empty block is fail-open (compat with cycles that pre-date
     ADR-0005).

Mode is taken from ``CLAUDE_SCOPE_WHITELIST_MODE``. Default is
``dryrun``. Promotion to ``enforce`` is a separate, explicit gate.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path, PurePosixPath
from typing import NamedTuple, Optional

# Make ``lib.common`` importable when launched directly as
# ``py -3 .../handlers/scope_check.py`` from the BAT wrapper. Mirrors
# ``secret_scan.py``.
_HANDLER_DIR = Path(__file__).resolve().parent
_HOOKS_ROOT = _HANDLER_DIR.parent
if str(_HOOKS_ROOT) not in sys.path:
    sys.path.insert(0, str(_HOOKS_ROOT))

from lib.common import (  # noqa: E402  (sys.path insert above)
    exit_allow,
    exit_block,
    exit_warn,
    get_cwd,
    get_env_override,
    log_event,
    parse_apply_patch,
    read_hook_input,
    run_handler,
)


_HOOK_NAME = "scope_check"
_EVENT = "PreToolUse"
_HARNESS_HOME = Path(os.environ.get("DINNER_HARNESS_HOME", str(_HOOKS_ROOT.parent))).resolve(strict=False)
_RULES_PATH = _HOOKS_ROOT / "rules" / "scope_protect.json"
# Handoff filename is overridable: the controller-side net drives builds from
# cfg.handoff_name, which is NOT always HANDOFF.md (/delegate always dispatches
# from HANDOFF_DELEGATE.md). Hardcoding the name made the handler miss the file
# and fail open, so that lane ran with no fence at all. Unset -> HANDOFF.md,
# which is what an interactive Claude session always uses.
# Basename only: the fence must stay inside DINNER_HARNESS_HOME. An absolute
# path or ``../`` here would redirect the whitelist at an arbitrary file, i.e.
# silently disarm the scope layer.
_HANDOFF_NAME_EXPLICIT = bool(os.environ.get("CLAUDE_SCOPE_HANDOFF_NAME"))
_HANDOFF_NAME = PurePosixPath(
    (os.environ.get("CLAUDE_SCOPE_HANDOFF_NAME") or "HANDOFF.md").replace("\\", "/")
).name
if _HANDOFF_NAME in ("", ".", ".."):  # PurePosixPath('..').name is '..', not ''
    _HANDOFF_NAME = "HANDOFF.md"
_HANDOFF_PATH = _HARNESS_HOME / _HANDOFF_NAME
# The fence itself, when the caller pins it instead of leaving it on disk (see
# _load_handoff_scope). Empty string is meaningful — "a fence was pinned and it
# bounds nothing" — so this is distinguished from unset, which means "read the
# file", the interactive path.
_FENCE_ENV = os.environ.get("CLAUDE_SCOPE_FENCE")
_FENCE_PINNED = _FENCE_ENV is not None
# "apply_patch" is Codex 0.149.0's file-edit tool (CODEX-COVERAGE.md §6.2, re-verified 2026-08-21 — see §6.5); it
# carries the patch in tool_input.command, not a single file_path. Inert on
# Claude (never emitted), active on Codex.
_TARGET_TOOLS = {"Edit", "Write", "apply_patch"}

# Absolute-path detector. Matches Windows ``C:/...`` / ``C:\...`` and
# POSIX-style ``/...``. Used in place of ``PurePath.is_absolute`` to
# keep behaviour identical regardless of host platform.
_ABS_RE = re.compile(r"^[A-Za-z]:[\\/]|^[\\/]")

# First ``` ```scope ``` fenced block in HANDOFF.md.
_SCOPE_BLOCK_RE = re.compile(
    r"^```scope\s*$(.*?)^```\s*$",
    re.DOTALL | re.MULTILINE,
)


class Pattern(NamedTuple):
    raw: str          # original entry text (for log / stderr)
    normalized: str   # absolute POSIX form, lowercase drive letter
    match_type: str   # "exact" | "prefix" | "glob"


def _drive_lower(posix_path: str) -> str:
    """Lowercase a Windows drive letter on a POSIX-form path."""
    if len(posix_path) >= 2 and posix_path[1] == ":":
        return posix_path[0].lower() + posix_path[1:]
    return posix_path


# Root of the always-block layer: the LIVE harness install, `~/.claude`. That
# is what the layer is for and what its docstring has always said — the rules
# name `settings.json` and `hooks/`, i.e. the harness that is in force.
#
# The two anchors that look plausible are both wrong. `_HARNESS_HOME` answers
# "where does the handoff live", and the net repoints it at the WORK REPO, so a
# target repo holding a root `settings.json` or a `hooks/` tree became
# undispatchable. `_HOOKS_ROOT.parent` — the tree this file happens to sit in —
# follows `cfg.hooks_dir`, which resolves to `<repo>/assets/claude/hooks`
# whenever orchestrate.py runs from a checkout: that anchors an unconditional,
# dryrun-exempt, fence-proof block list onto the harness repo's own sources, so
# a dispatched Builder could not edit the very files it is meant to maintain.
# Both leave the operator no escape but turning the hook off.
#
# Unchanged for an interactive session, where `~/.claude` IS the harness home.
def _install_home_posix() -> str:
    # Guarded: Path.home() raises RuntimeError on Windows when USERPROFILE,
    # HOME and HOMEDRIVE+HOMEPATH are all absent, and an unhandled raise here
    # exits the handler with code 1 — which the net reads as neither allow nor
    # block. The try/except is what prevents that; the call is still made at
    # import, which is fine because it can no longer fail.
    #
    # The fallback reconstructs `~/.claude` exactly in an INSTALLED layout
    # (handlers live at ~/.claude/hooks/handlers). From a repo checkout it
    # yields <repo>/assets/.claude, which exists nowhere, so the always-block
    # layer goes inert rather than protecting the wrong tree — the safe
    # direction for a case that needs three environment variables to be missing.
    try:
        home = Path.home()
    except Exception:  # noqa: BLE001 - no home is a configuration, not a crash
        home = _HOOKS_ROOT.parent.parent
    return _drive_lower((home / ".claude").resolve(strict=False).as_posix()).rstrip("/")


_INSTALL_HOME_POSIX = _install_home_posix()


def _classify_pattern(spec: str) -> str:
    # Wildcards win over the trailing separator. Checking the slash first made
    # `**/__pycache__/` a PREFIX entry, i.e. a literal directory named `**` — it
    # matched nothing, silently, and the operator's next move is to widen the
    # fence until something works. A directory entry that also globs is the
    # natural way to say "the build artifacts, wherever they land".
    #
    # `[` deliberately does NOT get that promotion. A bracket is legal in a
    # name (`docs/[archive]/` is ordinary in downloaded content, and `*`/`?` are
    # not even legal on NTFS), so promoting it turns a literal entry into a
    # character class: `docs/[draft]/` began admitting `docs/d/**` and rejecting
    # the very path it names. Wrong in both directions at once.
    #
    # That rule used to be applied only to DIRECTORY entries, because the
    # bracket test sat after the trailing-separator test. A FILE entry kept the
    # promotion, so a fence naming `[2026]resume.md` compiled to a class that
    # matches `2resume.md` and NOT the literal name the operator whitelisted:
    # blocked in enforce, while the message named the path that IS in the fence.
    # Bracketed names are ordinary in the document lane (`[2026]이력서.md`), and
    # the only move that message suggests is widening the fence — the anti-pattern
    # this net exists to avoid. Brackets are now literal everywhere unless the
    # entry ALSO carries a wildcard, i.e. unless the author opted into globbing.
    #
    # Residual, stated rather than hidden: inside an entry that does glob
    # (`[2026]docs/*.md`), `[...]` is still read as a class — the fence has no
    # escape syntax. That direction only ever fails closed (the entry matches
    # nothing), never widens.
    if any(ch in spec for ch in ("*", "?")):
        return "glob"
    if spec.endswith("/"):
        return "prefix"
    return "exact"


def _expand_dir_glob(spec: str) -> str:
    """`some/**/dir/` -> `some/**/dir/**`: a trailing slash means "everything
    under", which a glob has to spell out."""
    return spec + "**" if spec.endswith("/") else spec


def _normalize_path(path_str: str, cwd: Path) -> str:
    """Return an absolute POSIX path with lowercase drive letter."""
    if _ABS_RE.match(path_str):
        p = Path(path_str)
    else:
        p = cwd / path_str
    try:
        resolved = p.resolve(strict=False)
    except OSError:
        resolved = p
    return _drive_lower(resolved.as_posix())


def _glob_to_regex(pattern: str) -> str:
    """Translate a fence glob so ``*`` does NOT cross a path separator.

    ``fnmatch``'s ``*`` matches ``/`` happily, so a fence entry of ``src/*.py``
    also admitted ``src/deep/nested/evil.py`` — far wider than anyone writing
    that line intends, and the whole point of the entry is to bound where the
    Builder may write. ``**`` keeps the recursive meaning for callers that want
    it, and ``**/`` also matches zero directories so ``a/**/b`` still covers
    ``a/b``.
    """
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern.startswith("**/", i):
                out.append("(?:.*/)?")
                i += 3
            elif pattern.startswith("**", i):
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        if c == "[":
            j = i + 1
            if j < n and pattern[j] in ("!", "^"):
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:  # unterminated class -> literal '['
                out.append(re.escape("["))
                i += 1
                continue
            body = pattern[i + 1:j]
            if body[:1] in ("!", "^"):
                body = "^" + body[1:]
            out.append("[" + body.replace("\\", r"\\") + "]")
            i = j + 1
            continue
        out.append(re.escape(c))
        i += 1
    return "".join(out) + r"\Z"


def _matches(abs_path: str, pattern: Pattern) -> bool:
    target = pattern.normalized
    if pattern.match_type == "exact":
        return abs_path == target
    if pattern.match_type == "prefix":
        # Match on a path BOUNDARY, not on a string prefix. `Path.resolve()`
        # drops the trailing separator, so a bare `startswith` let the fence
        # entry `src/` admit `src-evil.py`, `srcret.env` and `src.py` — sibling
        # paths that merely share the spelling. Directory entries are the
        # common case for a code-lane fence, so this was wide open.
        #
        # rstrip because the two sources disagree on the trailing separator:
        # fence entries come through _normalize_path (resolve() drops it) while
        # always_block entries are string-joined from the ruleset (it stays).
        target = target.rstrip("/")
        return abs_path == target or abs_path.startswith(target + "/")
    if pattern.match_type == "glob":
        return re.match(_glob_to_regex(target), abs_path) is not None
    return False


def _load_always_block() -> list[Pattern]:
    """Load ``rules/scope_protect.json`` and return its ``always_block``
    list as normalised Pattern entries. On any error returns ``[]`` and
    logs ``error_internal`` — caller treats this as fail-open for the
    always-block layer (the scope-codeblock layer still runs).
    """
    try:
        with _RULES_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        log_event(
            _HOOK_NAME,
            event=_EVENT,
            decision="error_internal",
            reason=f"ruleset load failed: {type(exc).__name__}: {exc}",
        )
        return []

    out: list[Pattern] = []
    for entry in data.get("always_block", []) or []:
        match_type = entry.get("match")
        rel = entry.get("path", "") or ""
        if match_type not in {"exact", "prefix", "glob"} or not rel:
            log_event(
                _HOOK_NAME,
                event=_EVENT,
                decision="error_internal",
                reason=f"unknown match type {match_type!r} for path {rel!r}",
            )
            continue
        # Join the install prefix with the relative path. Both sides are
        # already canonical POSIX, so no resolve() is required.
        normalized = _INSTALL_HOME_POSIX + "/" + rel.lstrip("/")
        out.append(Pattern(raw=rel, normalized=normalized, match_type=match_type))
    return out


def _match_always_block(
    abs_path: str, entries: list[Pattern]
) -> Optional[Pattern]:
    """Return the first matching always-block Pattern, else None.

    Always-block applies only inside the harness install (Section 2 / 6.4) —
    the same root the entries are anchored to, so the gate and the patterns
    cannot disagree about which tree is being protected.
    """
    if not (
        abs_path == _INSTALL_HOME_POSIX
        or abs_path.startswith(_INSTALL_HOME_POSIX + "/")
    ):
        return None
    for entry in entries:
        if _matches(abs_path, entry):
            return entry
    return None


def _to_patterns(lines, cwd: Path) -> Optional[list[Pattern]]:
    """Fence entry lines -> Patterns. ``None`` when nothing usable is left."""
    patterns: list[Pattern] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match_type = _classify_pattern(line)
        spec = _expand_dir_glob(line) if match_type == "glob" else line
        patterns.append(
            Pattern(
                raw=line,
                normalized=_normalize_path(spec, cwd),
                match_type=match_type,
            )
        )
    return patterns if patterns else None


def _load_handoff_scope(cwd: Path) -> Optional[list[Pattern]]:
    """Parse the first ``` ```scope ``` block in HANDOFF.md and return
    its entries as normalised Pattern objects. Returns None when the
    file is missing, the block is absent, or the parsed block has no
    entries (fail-open semantics in the caller).
    """
    # A fence handed to us by the caller wins over the one on disk. This is
    # what closes the TOCTOU: the controller compares the handoff against what
    # it dispatched ONCE, but the scan that follows is two subprocesses per
    # changed file — seconds to minutes — and each of those re-read the fence
    # from disk at that moment. A Builder that rewrote the handoff inside that
    # window was rewriting the very rule it was about to be judged by, and the
    # controller never looked again. Carried in the environment the CONTROLLER
    # builds, so the Builder cannot reach it.
    if _FENCE_ENV is not None:
        return _to_patterns(_FENCE_ENV.splitlines(), cwd)

    if not _HANDOFF_PATH.is_file():
        log_event(
            _HOOK_NAME,
            event=_EVENT,
            decision="error_internal",
            reason=f"{_HANDOFF_NAME} not found",
        )
        return None
    try:
        # utf-8-sig tolerates a stray BOM (Open Question #4).
        text = _HANDOFF_PATH.read_text(encoding="utf-8-sig")
    except Exception as exc:
        log_event(
            _HOOK_NAME,
            event=_EVENT,
            decision="error_internal",
            reason=f"{_HANDOFF_NAME} read failed: {type(exc).__name__}: {exc}",
        )
        return None

    m = _SCOPE_BLOCK_RE.search(text)
    if m is None:
        return None
    return _to_patterns(m.group(1).splitlines(), cwd)


def _extract_paths(tool_name: str, tool_input: dict) -> list[str]:
    """Return the file paths a tool call targets.

    Edit/Write carry a single ``file_path``; Codex ``apply_patch`` carries a
    patch body in ``command`` referencing one or more paths.
    """
    if tool_name == "apply_patch":
        command = tool_input.get("command", "") or ""
        return [p for p, _ in parse_apply_patch(command)]
    file_path = tool_input.get("file_path", "") or ""
    return [file_path] if file_path else []


def main() -> None:
    payload = read_hook_input()

    mode_raw = get_env_override("CLAUDE_SCOPE_WHITELIST_MODE", "dryrun")
    mode = mode_raw if mode_raw in {"off", "dryrun", "enforce"} else "dryrun"

    if mode == "off":
        log_event(
            _HOOK_NAME,
            event=_EVENT,
            decision="allow",
            reason="mode=off",
        )
        exit_allow()

    tool_name = payload.get("tool_name")
    if tool_name not in _TARGET_TOOLS:
        # Out-of-scope tool — silent allow keeps log traffic down.
        exit_allow()

    tool_input = payload.get("tool_input") or {}
    raw_paths = _extract_paths(tool_name, tool_input)
    if not raw_paths:
        # No resolvable path (empty Edit/Write, or an apply_patch we could not
        # parse) — defer to the host.
        exit_allow()

    cwd = get_cwd(payload)
    abs_paths = [_normalize_path(p, cwd) for p in raw_paths]

    # Always-block: any targeted path inside the harness home blocks the call.
    always_entries = _load_always_block()
    for abs_path in abs_paths:
        hit = _match_always_block(abs_path, always_entries)
        if hit is not None:
            log_event(
                _HOOK_NAME,
                event=_EVENT,
                decision="block",
                reason=f"always_block:{hit.raw}",
                tool_name=tool_name,
                file_path=abs_path,
                match_pattern=hit.raw,
                match_type=hit.match_type,
                mode=mode,
            )
            exit_block(
                f"[scope_check:block] always-block: {abs_path} matched {hit.raw}"
            )

    scope_patterns = _load_handoff_scope(cwd)
    if not scope_patterns:
        # Fail-open is for the UNCONFIGURED case: no handoff named, none found,
        # i.e. an ordinary session that predates ADR-0005. It must not cover the
        # configured one. When a caller explicitly names the handoff via
        # CLAUDE_SCOPE_HANDOFF_NAME, a fence it cannot find is a broken policy
        # source, and silently allowing everything is the worst answer — block
        # in enforce, warn in dryrun.
        if (_HANDOFF_NAME_EXPLICIT or _FENCE_PINNED) and mode == "enforce":
            source = ("the fence pinned by the caller" if _FENCE_PINNED
                      else f"{_HANDOFF_NAME} (named via CLAUDE_SCOPE_HANDOFF_NAME)")
            log_event(_HOOK_NAME, event=_EVENT, decision="block",
                      reason=f"{source} carries no usable scope fence")
            exit_block(
                f"[scope_check:block] {source} has no usable ```scope``` fence"
            )
        exit_allow()

    # Scope codeblock: every targeted path must match an entry; the first
    # out-of-scope path warns (dryrun) or blocks (enforce).
    for abs_path in abs_paths:
        if any(_matches(abs_path, p) for p in scope_patterns):
            continue
        fields = {
            "event": _EVENT,
            "tool_name": tool_name,
            "file_path": abs_path,
            "mode": mode,
        }
        if mode == "enforce":
            log_event(
                _HOOK_NAME,
                decision="block",
                reason="out_of_scope",
                **fields,
            )
            exit_block(f"[scope_check:block] {abs_path} not in {_HANDOFF_NAME} scope")
        else:
            # dryrun (default) and any unknown mode value collapsed to dryrun.
            log_event(
                _HOOK_NAME,
                decision="warn",
                reason="out_of_scope (dryrun)",
                **fields,
            )
            exit_warn(f"[scope_check:warn:dryrun] {abs_path} not in {_HANDOFF_NAME} scope")

    exit_allow()


if __name__ == "__main__":
    run_handler(main, hook_name=_HOOK_NAME)
