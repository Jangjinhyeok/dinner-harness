# ADR-0014: centralize the Builder-vendor default in `harness.toml`

- **Status:** Accepted for canonical source; live installation remains a separate human end-sign-off gate
- **Date:** 2026-08-29
- **Deciders:** user + Architect session

## Context

ADR-0013's "Builder vendor 스위치" (from `3bb1538`) is a real switch, but not a
centralized one: the literal string `--builder codex` is copy-pasted into six
canonical documents (`content/instructions/CLAUDE.md`, `content/roles/ROLE_ARCHITECT.md`,
`content/rules/_mode/architect.md`, `content/skills/delegate/SKILL.md`,
`assets/claude/README.md`, `assets/codex/AGENTS.md`), each with its own prose telling
the reader to hand-edit that string to `--builder claude`. Flipping the default
correctly requires touching all six in sync; missing one leaves the harness giving
self-contradictory instructions depending on which doc a session happens to read.

The user asked to collapse this into a single source of truth in `harness.toml`,
matching the existing precedent: `settings.json.template` already resolves
`<CLAUDE_HOME>`/`<USERNAME>` tokens at install time via `adapters/claude.py`'s generic
template-substitution loop (`harness.toml [vars]` → `.replace()` chain).

Two structural obstacles surfaced during design:

1. Three of the six files are not individually addressable in `harness.toml` — they
   are swept in by a whole-directory `copy` entry (`content/roles` → `roles`,
   `content/rules` → `rules`, `content/skills` → `skills`). The adapter has no
   filename-level exclude, only `exclude_dir_names`/`exclude_file_suffixes`.
2. `adapters/codex.py` has no generic template-substitution step at all — its `install()`
   only implements `copy`/`skills_*`/`hooks_*`/`agents_*`, so `assets/codex/AGENTS.md`
   (a plain `copy` entry today) cannot resolve a token without new adapter code.

## Decision

Add `builder_vendor` (the actual value, default `"codex"`) and `builder_vendor_token`
(the placeholder string, `"<BUILDER_VENDOR>"`) to `harness.toml [vars]`. Replace the
literal `--builder codex` in all six canonical documents with `--builder
<BUILDER_VENDOR>`, and render that token at install time — extending
`adapters/claude.py`'s existing substitution chain, and adding an equivalent minimal
substitution step to `adapters/codex.py` (text-only, no JSON strip_keys/merge needed,
since `AGENTS.md` is not JSON). Switching the default becomes: edit one line in
`harness.toml`, then `py -3 refresh.py --apply`.

## Implementation Guidelines

- **`content/roles` and `content/rules` (small, ≤4 files each): split the directory
  `copy` entry into explicit per-file entries** in `harness.toml` rather than adding a
  filename-exclude mechanism — `ROLE_BUILDER.md`/`agent-routing.md`/`autonomy-policy.md`/
  `_mode/builder.md` stay plain `copy`; `ROLE_ARCHITECT.md`/`_mode/architect.md` move to
  `template`. This avoids new adapter exclude logic for a two-and-four-file directory.
- **`content/skills` (29 directories): do NOT split.** Enumerating every skill just to
  carve out one file is disproportionate. Instead, leave the existing bulk `copy` entry
  untouched and add ONE `template` entry for `content/skills/delegate/SKILL.md` with the
  same `dest`. `install()`'s copy pass runs before its template pass, so the template
  step's write is the one that lands on disk; the earlier plain copy of the same path is
  harmless (`check_install()` re-reads the final on-disk bytes for both plan entries, so
  the duplicate registration does not produce false drift — verify this understanding
  against `check.py`'s `check_install()` before trusting it, since it wasn't unit-tested
  for this specific double-registration shape before this ADR).
- **`content/instructions/CLAUDE.md` and `assets/claude/README.md`**: already single-file
  `copy` entries — just move them to `template`.
- **`assets/codex/AGENTS.md`**: move from `[targets.codex].copy` to a new
  `[targets.codex].template` list; `adapters/codex.py` needs a new small loop added to
  `install()` (after its existing copy/skills/hooks/agents steps) that reads
  `target_cfg.get("template", [])`, does `src.read_text(...).replace(builder_vendor_token,
  builder_vendor)`, and writes the result — mirror `adapters/claude.py`'s non-JSON branch
  only; do not port the JSON `strip_keys`/`merge` machinery, nothing in the codex target
  needs it.
- **Six docs**: replace the literal `--builder codex` substring in each file's dispatch
  command with `--builder <BUILDER_VENDOR>`. Do not touch any other content in these
  files beyond the specific substitutions this HANDOFF names.
- **Explanatory prose that assumed hand-editing N files is now wrong** and must be
  rewritten (not just the literal token): CLAUDE.md's "Builder vendor 스위치" paragraph,
  ROLE_ARCHITECT.md's dispatch-line aside sentence, `README.md`/`README.en.md`'s "단일
  vendor만 사용하는 경우"/"Using only one vendor" Claude-only paragraph. The new
  mechanism to describe: edit `harness.toml`'s `[vars].builder_vendor`, then `py -3
  refresh.py --apply`.
- **Test update**: `orchestrator/tests/test_orchestrator.py`'s
  `test_architect_and_delegate_document_an_unpiped_absolute_dispatch_shape` hardcodes
  `--builder codex` in its expected `architect_cmd` string — update to `--builder
  <BUILDER_VENDOR>`, since the canonical *source* files now contain the placeholder, not
  the resolved value (this test reads `content/`-relative source files directly, not
  rendered installs).
- **`curation.toml` re-bless required** (`py -3 check.py --update`) since
  `content/instructions/CLAUDE.md`'s bytes change.

## Consequences

- **Positive:** switching the Builder-vendor default is one line in `harness.toml` plus
  a re-render — no more N-file hand-sync, no more silent drift between docs.
- **Positive:** the mechanism generalizes — a future harness-wide default that needs to
  appear in prose across multiple docs can reuse the same `[vars]` + template-token
  pattern instead of inventing a new one.
- **Negative / trade-offs:** `adapters/codex.py` gains a second install "shape" (copy +
  now also template), duplicating a small amount of logic already in `adapters/claude.py`
  — acceptable now (single new loop, ~10 lines) but a second such addition should prompt
  extracting a shared `lib/render.py` helper instead of a third copy-paste.
- **Negative / trade-offs:** the `content/skills/delegate/SKILL.md` double-registration
  (present in both `copy` and `template` plan entries for the same `dest`) is a mild
  wart — a future reader of `harness.toml` needs the code comment explaining why, since
  the file isn't visibly "special" from the manifest structure alone.
- **Follow-ups:** none identified; `orchestrator/README.md`/`README.ko.md`'s advanced
  `$claudeHome`-flavored examples don't show `--builder` at all and are unaffected.

## Alternatives considered

- **Add a filename-level `exclude_file_names` to `_copy_tree`/`_excluded`, then list
  every affected file as an explicit `copy`/`template` pair:** rejected for
  `content/skills` — would require enumerating (or exclude-listing) one file out of 29
  directories, a maintenance liability every time a new skill is added, for no benefit
  over the double-registration approach.
- **Leave `assets/codex/AGENTS.md` un-centralized (accept 5-of-6 centralization,
  hand-edit AGENTS.md separately):** rejected — the whole point was to remove manual
  sync entirely; leaving one file out defeats it and is a worse asymmetry than today's
  fully-manual six.
