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
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Repo root = parent of this package's parent (orchestrator/ lives at repo root),
# same resolution orchestrator/config.py already uses.
_REPO_ROOT = Path(__file__).resolve().parent.parent

# The only code-level constant this module permits: which preset NAME to look
# up in routing.toml when the caller doesn't specify one. This is not a model
# mapping — it names nothing concrete, only a key into the real SSOT.
DEFAULT_PRESET = "codex_only"

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


def validate_profile(profile: ModelProfile) -> ModelProfile:
    """Static contract only; installed CLI and account access remain separate checks."""
    if profile.vendor not in _VALID_VENDORS:
        raise RoutingConfigError(f"invalid vendor: {profile.vendor!r}")
    if not isinstance(profile.model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]*", profile.model):
        raise RoutingConfigError("model must be a non-empty model identifier without whitespace")
    efforts = {"codex": ("low", "medium", "high", "xhigh"), "claude": ("low", "medium", "high", "max")}
    if profile.effort not in efforts[profile.vendor]:
        raise RoutingConfigError(f"unsupported effort {profile.effort!r} for vendor {profile.vendor!r}")
    if (profile.vendor == "codex" and profile.model.startswith("claude-")) or (profile.vendor == "claude" and profile.model.startswith("gpt-")):
        raise RoutingConfigError("model identifier conflicts with the selected vendor")
    return profile


def policy_digest(config: dict[str, Any], preset: str) -> str:
    """Bind evidence to the selected policy, including explicit fallback profiles."""
    resolve_profile(config, preset, "challenger_high")
    payload = {"preset": preset, "presets": config["presets"]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


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
    if not isinstance(name, str) or not name.strip() or name != name.strip():
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
    unknown = set(role_table) - {"vendor", "model", "effort"}
    if unknown:
        raise RoutingConfigError(f"unknown profile field(s): {', '.join(sorted(unknown))}")
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
    return validate_profile(ModelProfile(vendor=vendor, model=role_table["model"], effort=role_table["effort"]))


def resolve_profile_for_vendor(
    config: dict[str, Any], preset: str, logical_role: str, vendor: str,
) -> ModelProfile:
    """Resolve an override through the active preset's explicit compatibility map."""
    profile = resolve_profile(config, preset, logical_role)
    if vendor == profile.vendor:
        return profile
    if vendor not in _VALID_VENDORS:
        raise RoutingConfigError(f"invalid vendor override: {vendor!r}")
    mapping = config["presets"][preset].get("vendor_fallbacks", {})
    if not isinstance(mapping, dict):
        raise RoutingConfigError("vendor_fallbacks must be a vendor-to-preset table")
    target = mapping.get(vendor)
    if not isinstance(target, str) or not target:
        raise RoutingConfigError(f"missing or ambiguous explicit fallback for {preset!r}/{vendor!r}")
    profile = resolve_profile(config, target, logical_role)
    if profile.vendor != vendor:
        raise RoutingConfigError(f"fallback {target!r} does not select vendor {vendor!r}")
    return profile


def resolve_builder_high_for_vendor(
    config: dict[str, Any], vendor: str, preset: str | None = None,
) -> ModelProfile:
    return resolve_profile_for_vendor(config, preset or active_preset_name(config), "builder_high", vendor)
