"""Load and validate declarative encode and subtitle-style profiles from configs/."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Invalid or missing configuration (clear message for CLI users)."""


@dataclass(frozen=True)
class EncodeProfile:
    id: str
    width: int
    height: int
    frame_rate: int
    video_filter: str
    video_codec: str
    crf: int
    encoder_preset: str
    audio_codec: str
    audio_bitrate_kbps: int


@dataclass(frozen=True)
class SubtitleStyle:
    id: str
    font_family: str
    font_size: int
    primary_color: str
    outline_color: str
    outline_width: int
    margin_v: int
    alignment: int


_STT_ENGINES = frozenset({"stub", "whisper_cli", "faster_whisper"})


@dataclass(frozen=True)
class SpeechToTextConfig:
    """Local-first STT: ``stub``, OpenAI ``whisper_cli``, or optional ``faster_whisper``."""

    engine: str
    model: str
    language: str


@dataclass(frozen=True)
class PipelineConfig:
    encode_profiles: dict[str, EncodeProfile]
    subtitle_styles: dict[str, SubtitleStyle]
    stt: SpeechToTextConfig
    config_dir: Path


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resolve_config_dir(explicit: Path | None) -> Path:
    """Resolve config directory: explicit, else ./configs if present, else <repo>/configs."""
    if explicit is not None:
        p = explicit.expanduser().resolve()
        if not p.is_dir():
            raise ConfigError(
                f"Config directory does not exist or is not a directory: {p}"
            )
        return p
    cwd_cfg = (Path.cwd() / "configs").resolve()
    if cwd_cfg.is_dir():
        return cwd_cfg
    fallback = (_package_root() / "configs").resolve()
    if not fallback.is_dir():
        raise ConfigError(
            "No configs/ directory found. Expected ./configs from the current working directory "
            f"or bundled configs at {fallback}. Use --config-dir to set the path explicitly."
        )
    return fallback


def _expect_str(obj: dict[str, object], key: str, path: str) -> str:
    v = obj.get(key)
    if not isinstance(v, str) or not v.strip():
        raise ConfigError(f"{path}: missing or invalid string field {key!r}")
    return v.strip()


def _expect_int(obj: dict[str, object], key: str, path: str) -> int:
    v = obj.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise ConfigError(f"{path}: field {key!r} must be an integer")
    return v


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read config file {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: root must be a JSON object")
    return data


def _video_filter_proves_output_dimensions(vf: str, width: int, height: int) -> bool:
    """True if *vf* contains an explicit WxH proof matching *width*×*height*.

    ``crop=`` / ``pad=`` are taken as authoritative when present (final frame size).
    ``scale=WxH`` counts only when there is no ``crop=`` or ``pad=`` in the chain,
    otherwise an intermediate scale could disagree with a later crop/pad.
    """
    crop_n = f"crop={width}:{height}"
    pad_n = f"pad={width}:{height}"
    scale_n = f"scale={width}:{height}"
    if crop_n in vf or pad_n in vf:
        return True
    if "crop=" in vf or "pad=" in vf:
        return False
    return scale_n in vf


def _parse_encode_profile(data: dict[str, object], source: str) -> EncodeProfile:
    pid = _expect_str(data, "id", source)
    width = _expect_int(data, "width", source)
    height = _expect_int(data, "height", source)
    frame_rate = _expect_int(data, "frame_rate", source)
    vf = _expect_str(data, "video_filter", source)
    vcodec = _expect_str(data, "video_codec", source)
    crf = _expect_int(data, "crf", source)
    preset = _expect_str(data, "encoder_preset", source)
    acodec = _expect_str(data, "audio_codec", source)
    ab = _expect_int(data, "audio_bitrate_kbps", source)
    if width < 16 or height < 16:
        raise ConfigError(f"{source}: width and height must be at least 16")
    if frame_rate < 1:
        raise ConfigError(f"{source}: frame_rate must be >= 1")
    if crf < 0 or crf > 51:
        raise ConfigError(f"{source}: crf must be between 0 and 51")
    if ab < 8:
        raise ConfigError(f"{source}: audio_bitrate_kbps must be at least 8")
    if re.search(r"[\n\r;]", vf):
        raise ConfigError(f"{source}: video_filter must be a single-line filter string")
    if not _video_filter_proves_output_dimensions(vf, width, height):
        crop_n = f"crop={width}:{height}"
        pad_n = f"pad={width}:{height}"
        scale_n = f"scale={width}:{height}"
        raise ConfigError(
            f"{source}: video_filter must contain at least one of {crop_n!r}, {pad_n!r}, "
            f"or {scale_n!r} so the output frame matches encode width×height ({width}×{height})."
        )
    return EncodeProfile(
        id=pid,
        width=width,
        height=height,
        frame_rate=frame_rate,
        video_filter=vf,
        video_codec=vcodec,
        crf=crf,
        encoder_preset=preset,
        audio_codec=acodec,
        audio_bitrate_kbps=ab,
    )


def _parse_subtitle_style(data: dict[str, object], source: str) -> SubtitleStyle:
    sid = _expect_str(data, "id", source)
    font = _expect_str(data, "font_family", source)
    size = _expect_int(data, "font_size", source)
    primary = _expect_str(data, "primary_color", source)
    outline_c = _expect_str(data, "outline_color", source)
    ow = _expect_int(data, "outline_width", source)
    margin_v = _expect_int(data, "margin_v", source)
    align = _expect_int(data, "alignment", source)
    if size < 8:
        raise ConfigError(f"{source}: font_size must be >= 8")
    if ow < 0:
        raise ConfigError(f"{source}: outline_width must be >= 0")
    if margin_v < 0:
        raise ConfigError(f"{source}: margin_v must be >= 0")
    if align < 1 or align > 11:
        raise ConfigError(
            f"{source}: alignment must be between 1 and 11 (ASS alignment)"
        )
    return SubtitleStyle(
        id=sid,
        font_family=font,
        font_size=size,
        primary_color=primary,
        outline_color=outline_c,
        outline_width=ow,
        margin_v=margin_v,
        alignment=align,
    )


def _parse_stt(data: dict[str, object], source: str) -> SpeechToTextConfig:
    engine = _expect_str(data, "engine", source).lower()
    if engine not in _STT_ENGINES:
        raise ConfigError(
            f"{source}: engine must be one of {sorted(_STT_ENGINES)}; got {engine!r}"
        )
    model = data.get("model")
    if model is None:
        model_s = ""
    elif isinstance(model, str):
        model_s = model.strip()
    else:
        raise ConfigError(f"{source}: field 'model' must be a string")
    lang_v = data.get("language", "")
    if lang_v is None:
        language = ""
    elif isinstance(lang_v, str):
        language = lang_v.strip()
    else:
        raise ConfigError(f"{source}: field 'language' must be a string")
    if engine in ("whisper_cli", "faster_whisper") and not model_s:
        raise ConfigError(
            f"{source}: model must be non-empty when engine is {engine!r} "
            "(e.g. tiny, base, small)."
        )
    return SpeechToTextConfig(engine=engine, model=model_s, language=language)


def load_pipeline_config(config_dir: Path | None = None) -> PipelineConfig:
    """Load all encode and subtitle style profiles from *config_dir*."""
    root = resolve_config_dir(config_dir)
    encode_dir = root / "encode"
    styles_dir = root / "subtitle_styles"
    if not encode_dir.is_dir():
        raise ConfigError(
            f"Missing encode profiles directory: {encode_dir}. "
            "Expected a subdirectory named 'encode' with one JSON file per profile."
        )
    if not styles_dir.is_dir():
        raise ConfigError(
            f"Missing subtitle_styles directory: {styles_dir}. "
            "Expected a subdirectory named 'subtitle_styles' with one JSON file per style."
        )

    encode_profiles: dict[str, EncodeProfile] = {}
    for path in sorted(encode_dir.glob("*.json")):
        data = _load_json_object(path)
        prof = _parse_encode_profile(data, str(path))
        stem = path.stem
        if prof.id != stem:
            raise ConfigError(
                f"{path}: 'id' field {prof.id!r} must match file name stem {stem!r}"
            )
        if prof.id in encode_profiles:  # pragma: no cover
            raise ConfigError(f"Duplicate encode profile id {prof.id!r}")  # pragma: no cover
        encode_profiles[prof.id] = prof

    subtitle_styles: dict[str, SubtitleStyle] = {}
    for path in sorted(styles_dir.glob("*.json")):
        data = _load_json_object(path)
        style = _parse_subtitle_style(data, str(path))
        stem = path.stem
        if style.id != stem:
            raise ConfigError(
                f"{path}: 'id' field {style.id!r} must match file name stem {stem!r}"
            )
        if style.id in subtitle_styles:  # pragma: no cover
            raise ConfigError(f"Duplicate subtitle style id {style.id!r}")  # pragma: no cover
        subtitle_styles[style.id] = style

    if not encode_profiles:
        raise ConfigError(f"No encode profiles found under {encode_dir}")
    if len(subtitle_styles) < 2:
        raise ConfigError(
            f"At least two subtitle style presets are required under {styles_dir}; "
            f"found {len(subtitle_styles)}."
        )

    stt_path = root / "stt.json"
    if not stt_path.is_file():
        raise ConfigError(
            f"Missing speech-to-text config: {stt_path}. "
            "Add stt.json with engine, model, and language (see bundled configs/stt.json)."
        )
    stt_data = _load_json_object(stt_path)
    stt = _parse_stt(stt_data, str(stt_path))

    return PipelineConfig(
        encode_profiles=encode_profiles,
        subtitle_styles=subtitle_styles,
        stt=stt,
        config_dir=root,
    )


def require_encode_profile(cfg: PipelineConfig, profile_id: str) -> EncodeProfile:
    try:
        return cfg.encode_profiles[profile_id]
    except KeyError as exc:
        available = ", ".join(sorted(cfg.encode_profiles))
        raise ConfigError(
            f"Unknown encode profile {profile_id!r}. Available profiles: {available}."
        ) from exc


def require_subtitle_style(cfg: PipelineConfig, style_id: str) -> SubtitleStyle:
    try:
        return cfg.subtitle_styles[style_id]
    except KeyError as exc:
        available = ", ".join(sorted(cfg.subtitle_styles))
        raise ConfigError(
            f"Unknown subtitle style {style_id!r}. Available styles: {available}."
        ) from exc
