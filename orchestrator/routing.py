"""Logical-profile routing: preset -> role -> concrete vendor/model/effort.

The ONLY place concrete model/vendor/effort literals may live is
``content/routing.toml`` (dev) / ``routing.toml`` (installed) — see ADR-0020.
This module never hardcodes a model mapping as a fallback: a missing or
invalid routing config is a hard ``RoutingConfigError``, never a silent
fallback to a duplicated mapping. The only code-level constant permitted is
the *name* of the default preset to look up inside that same file.

Stdlib only (tomllib).
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Repo root = parent of this package's parent (orchestrator/ lives at repo root),
# same resolution orchestrator/config.py already uses.
_REPO_ROOT = Path(__file__).resolve().parent.parent

# The only code-level constant this module permits: which preset NAME to look
# up in routing.toml when the caller doesn't specify one. This is not a model
# mapping — it names nothing concrete, only a key into the real SSOT.
DEFAULT_PRESET = "hybrid"

_VALID_VENDORS = ("codex", "claude")


class RoutingConfigError(Exception):
    """routing.toml is missing, unparseable, or missing a required preset/profile/key.

    Deliberately fail-closed: the caller must not catch this and substitute a
    hardcoded mapping (see ADR-0020 correction 1).
    """


@dataclass(frozen=True)
class ModelProfile:
    vendor: str
    model: str
    effort: str


def default_routing_path(repo_root: Path | None = None) -> Path:
    """Dev vs installed routing.toml location, mirroring
    ``orchestrator.config._resolve_hooks_dir``'s exact dev/installed pattern:
    dev tree keeps it under ``content/``, an installed tree has it at the
    install root alongside ``orchestrate.py``.
    """
    root = repo_root if repo_root is not None else _REPO_ROOT
    dev = root / "content" / "routing.toml"
    installed = root / "routing.toml"
    return dev if dev.is_file() else installed


def load_routing_config(path: Path) -> dict[str, Any]:
    """Parse routing.toml from an explicit path. Raises RoutingConfigError on
    any failure — missing file, invalid TOML, or missing top-level [routing]/
    [presets] tables. No fallback."""
    if not path.is_file():
        raise RoutingConfigError(
            f"routing config not found: {path} — this is a hard configuration "
            "error, not something the harness silently works around. Create "
            "content/routing.toml (see ADR-0020) or pass an explicit path."
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as exc:
        raise RoutingConfigError(f"routing config at {path} failed to parse: {exc}") from exc
    routing_table = data.get("routing")
    if not isinstance(routing_table, dict) or "preset" not in routing_table:
        raise RoutingConfigError(
            f"routing config at {path} is missing a [routing] table with a "
            "'preset' key"
        )
    if "presets" not in data or not isinstance(data["presets"], dict):
        raise RoutingConfigError(f"routing config at {path} is missing a [presets] table")
    return data


def active_preset_name(config: dict[str, Any]) -> str:
    """The preset routing.toml itself declares active, via [routing].preset."""
    routing_table = config.get("routing", {})
    if not isinstance(routing_table, dict):
        raise RoutingConfigError("routing config's [routing] table is not a table")
    name = routing_table.get("preset")
    if not name or not isinstance(name, str):
        raise RoutingConfigError("routing config's [routing].preset is missing or not a string")
    return name


def resolve_profile(config: dict[str, Any], preset: str, logical_role: str) -> ModelProfile:
    """Look up preset.logical_role in an already-loaded routing config.

    Raises RoutingConfigError if the preset or the role within it is missing,
    or if the entry is missing a required key or has an invalid vendor."""
    presets = config.get("presets", {})
    if not isinstance(presets, dict):
        raise RoutingConfigError("routing config's [presets] table is not a table")
    if preset not in presets:
        available = ", ".join(sorted(presets)) or "(none defined)"
        raise RoutingConfigError(
            f"routing preset {preset!r} is not defined in routing.toml "
            f"(available: {available})"
        )
    preset_table = presets[preset]
    if not isinstance(preset_table, dict):
        raise RoutingConfigError(f"routing preset {preset!r} is not a table")
    role_table = preset_table.get(logical_role)
    if role_table is None:
        available_roles = ", ".join(sorted(preset_table)) or "(none defined)"
        raise RoutingConfigError(
            f"logical role {logical_role!r} is not defined under preset "
            f"{preset!r} (available roles: {available_roles})"
        )
    if not isinstance(role_table, dict):
        raise RoutingConfigError(
            f"preset {preset!r} role {logical_role!r} must be a table"
        )
    missing = [k for k in ("vendor", "model", "effort") if k not in role_table]
    if missing:
        raise RoutingConfigError(
            f"preset {preset!r} role {logical_role!r} is missing required "
            f"key(s): {', '.join(missing)}"
        )
    invalid_types = [
        k for k in ("vendor", "model", "effort") if not isinstance(role_table[k], str)
    ]
    if invalid_types:
        raise RoutingConfigError(
            f"preset {preset!r} role {logical_role!r} has non-string "
            f"key(s): {', '.join(invalid_types)}"
        )
    vendor = role_table["vendor"]
    if vendor not in _VALID_VENDORS:
        raise RoutingConfigError(
            f"preset {preset!r} role {logical_role!r} has invalid vendor "
            f"{vendor!r} (must be one of {_VALID_VENDORS})"
        )
    return ModelProfile(vendor=vendor, model=role_table["model"], effort=role_table["effort"])


def resolve_builder_high_for_vendor(config: dict[str, Any], vendor: str) -> ModelProfile:
    """Find a builder_high profile for an explicitly-overridden vendor, searching
    every preset defined in routing.toml (not just the active one).

    Used when a HIGH-tier dispatch carries an explicit ``--builder <vendor>``
    override: the concrete builder_high model/effort for that vendor still
    comes only from routing.toml (never an arbitrary CLI model string — see
    ADR-0020 correction 4). Raises RoutingConfigError if no preset defines a
    builder_high profile for that vendor — this must fail closed, not silently
    pick an unrelated profile.
    """
    if vendor not in _VALID_VENDORS:
        raise RoutingConfigError(f"invalid vendor override: {vendor!r}")
    presets = config.get("presets", {})
    if not isinstance(presets, dict):
        raise RoutingConfigError("routing config's [presets] table is not a table")
    for preset_name in sorted(presets):
        preset_table = presets[preset_name]
        if not isinstance(preset_table, dict):
            raise RoutingConfigError(f"routing preset {preset_name!r} is not a table")
        role_table = preset_table.get("builder_high")
        if role_table is None:
            continue
        if not isinstance(role_table, dict):
            raise RoutingConfigError(
                f"preset {preset_name!r} role 'builder_high' must be a table"
            )
        if role_table.get("vendor") == vendor:
            missing = [k for k in ("vendor", "model", "effort") if k not in role_table]
            if missing:
                continue
            invalid_types = [
                k for k in ("vendor", "model", "effort")
                if not isinstance(role_table[k], str)
            ]
            if invalid_types:
                raise RoutingConfigError(
                    f"preset {preset_name!r} role 'builder_high' has non-string "
                    f"key(s): {', '.join(invalid_types)}"
                )
            return ModelProfile(
                vendor=role_table["vendor"], model=role_table["model"], effort=role_table["effort"]
            )
    raise RoutingConfigError(
        f"no preset in routing.toml defines a builder_high profile for vendor "
        f"{vendor!r} — cannot honor this HIGH-tier vendor override"
    )
