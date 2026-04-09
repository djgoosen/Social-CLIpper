"""Job preset JSON (FR7): safe load/save of profile, subtitle style, optional config dir."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from social_clipr.pipeline import validate_subtitle_font_size

JOB_PRESET_VERSION = 1

# Identifiers: encode profile id, subtitle style id (alphanumeric + safe punctuation).
_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")


class JobPresetError(ValueError):
    """Invalid preset file or unsafe field values."""


def _reject_shell_metacharacters(s: str, field: str) -> None:
    if "\x00" in s or "\n" in s or "\r" in s:
        raise JobPresetError(f"{field} contains invalid control characters")
    for ch in ";|&$`<>\\":
        if ch in s:
            raise JobPresetError(f"{field} contains disallowed character {ch!r}")


def _expect_id(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JobPresetError(f"{field} must be a non-empty string")
    s = value.strip()
    _reject_shell_metacharacters(s, field)
    if not _ID_RE.fullmatch(s):
        raise JobPresetError(
            f"{field} must match [a-zA-Z0-9][a-zA-Z0-9_.-]* (got {s!r})"
        )
    return s


def _expect_subtitle_font_size_opt(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise JobPresetError(f"{field} must be an integer or null")
    try:
        validate_subtitle_font_size(value)
    except ValueError as exc:
        raise JobPresetError(str(exc)) from exc
    return value


def load_job_preset(path: Path) -> dict[str, Any]:
    """Load and validate a job preset.

    Returns keys: ``profile``, ``subtitle_style``, ``config_dir``, ``subtitle_font_size``
    (optional int or ``None``).
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise JobPresetError(f"Cannot read preset {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JobPresetError(f"Invalid JSON in preset {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise JobPresetError("Preset root must be a JSON object")
    ver = data.get("version")
    if ver != JOB_PRESET_VERSION:
        raise JobPresetError(
            f"Unsupported preset version {ver!r}; expected {JOB_PRESET_VERSION}"
        )
    profile = _expect_id(data.get("profile"), "profile")
    subtitle_style = _expect_id(data.get("subtitle_style"), "subtitle_style")
    config_dir_raw = data.get("config_dir")
    config_dir: Path | None = None
    if config_dir_raw is not None:
        if not isinstance(config_dir_raw, str):
            raise JobPresetError("config_dir must be a string or null")
        s = config_dir_raw.strip()
        if not s:
            raise JobPresetError("config_dir, if set, must be non-empty")
        _reject_shell_metacharacters(s, "config_dir")
        config_dir = Path(s).expanduser()
    subtitle_font_size = _expect_subtitle_font_size_opt(
        data.get("subtitle_font_size"), "subtitle_font_size"
    )
    return {
        "profile": profile,
        "subtitle_style": subtitle_style,
        "config_dir": config_dir,
        "subtitle_font_size": subtitle_font_size,
    }


def save_job_preset(
    path: Path,
    *,
    profile: str,
    subtitle_style: str,
    config_dir: Path | None = None,
    subtitle_font_size: int | None = None,
) -> None:
    """Write a versioned job preset (UTF-8 JSON, sorted keys)."""
    profile = _expect_id(profile, "profile")
    subtitle_style = _expect_id(subtitle_style, "subtitle_style")
    if subtitle_font_size is not None:
        _expect_subtitle_font_size_opt(subtitle_font_size, "subtitle_font_size")
    payload: dict[str, Any] = {
        "version": JOB_PRESET_VERSION,
        "profile": profile,
        "subtitle_style": subtitle_style,
    }
    if subtitle_font_size is not None:
        payload["subtitle_font_size"] = subtitle_font_size
    else:
        payload["subtitle_font_size"] = None
    if config_dir is not None:
        p = config_dir.expanduser().resolve()
        if not p.is_dir():
            raise JobPresetError(f"config_dir is not a directory: {p}")
        payload["config_dir"] = str(p)
    else:
        payload["config_dir"] = None
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
