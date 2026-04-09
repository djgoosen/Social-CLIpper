"""Render stage: profile-specific output video (FFmpeg) or stub copy."""

from __future__ import annotations

import errno
import os
import re
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from social_clipr.bundle import rendered_video_filename
from social_clipr.config_loader import EncodeProfile, SubtitleStyle


class RenderError(RuntimeError):
    """Raised when render cannot produce the output file."""


# FFmpeg's SubRip demux path builds an ASS header with PlayRes 384×288
# (``ff_ass_subtitle_header_default`` in libavcodec). ``force_style`` values are
# interpreted in that script space; treating them as output-frame pixels (e.g.
# MarginV=160 on a 1080px-tall frame) anchors cues near the vertical middle.
_FFMPEG_SRT_ASS_PLAYRES_Y = 288


def _scale_subtitle_style_for_ffmpeg_srt(
    style: SubtitleStyle, output_height: int
) -> SubtitleStyle:
    """Map config fields (meant as output pixels) to FFmpeg SRT→ASS PlayResY units."""
    if output_height <= 0:
        raise RenderError(
            f"encode profile height must be positive for subtitle scaling; got {output_height}"
        )
    factor = _FFMPEG_SRT_ASS_PLAYRES_Y / output_height
    ow = style.outline_width
    outline_scaled = max(1, round(ow * factor)) if ow > 0 else 0
    return replace(
        style,
        font_size=max(1, round(style.font_size * factor)),
        margin_v=max(0, round(style.margin_v * factor)),
        outline_width=outline_scaled,
    )


def _ffmpeg_path() -> str | None:
    """Resolve FFmpeg binary: ``SOCIAL_CLIPR_FFMPEG`` (path or ``PATH`` name), else ``ffmpeg`` on ``PATH``."""
    override = os.environ.get("SOCIAL_CLIPR_FFMPEG", "").strip()
    if override:
        expanded = Path(override).expanduser()
        # Bare command name (no path): resolve only via PATH. Otherwise a file named
        # ``ffmpeg`` in the current working directory (e.g. a wrong-OS download) can
        # shadow the real system binary and raise Exec format error at runtime.
        command_only = (
            not expanded.is_absolute()
            and os.sep not in override
            and not (os.altsep and os.altsep in override)
        )
        if command_only:
            return shutil.which(override)
        if expanded.is_file():
            return str(expanded.resolve())
        return shutil.which(override)
    return shutil.which("ffmpeg")


def _normalize_ass_colour(token: str) -> str:
    """Normalize config ASS-like colours to &HAABBGGRR& for libass force_style."""
    t = token.strip()
    if not (t.startswith("&H") and t.endswith("&")):
        raise RenderError(
            f"Subtitle colour must look like &HBBGGRR& or &HAABBGGRR&; got {token!r}"
        )
    inner = t[2:-1].upper()
    if not re.fullmatch(r"[0-9A-F]+", inner):
        raise RenderError(f"Invalid hex in subtitle colour: {token!r}")
    if len(inner) == 6:
        return f"&H00{inner}&"
    if len(inner) == 8:
        return f"&H{inner}&"
    raise RenderError(
        f"Subtitle colour hex must be 6 or 8 digits after &H; got {token!r}"
    )


def _force_style_arg(style: SubtitleStyle) -> str:
    """Comma-separated libass force_style= value (no outer quotes)."""
    pc = _normalize_ass_colour(style.primary_color)
    oc = _normalize_ass_colour(style.outline_color)
    parts = [
        f"FontName={style.font_family}",
        f"FontSize={style.font_size}",
        f"PrimaryColour={pc}",
        f"OutlineColour={oc}",
        f"Outline={style.outline_width}",
        f"MarginV={style.margin_v}",
        f"Alignment={style.alignment}",
    ]
    return ",".join(parts)


def _force_style_token_for_subtitles_filter(style: SubtitleStyle) -> str:
    """Build ``force_style=`` value for ``-vf`` filterchains.

    The filter **graph** splits on ``,`` between filters *before* subtitles parses
    its options, so each comma in the ASS style list must be written as ``\\,``.
    """
    raw = _force_style_arg(style)
    return raw.replace("\\", r"\\").replace("'", r"\'").replace(",", r"\,")


def _subtitles_srt_token(name: str) -> str:
    """Filename only for ``subtitles=`` (used with ``cwd`` = job dir).

    Leading ``/`` is reserved in libavfilter (``/opt`` = load-from-file).
    """
    if name != Path(name).name or "/" in name or "\\" in name or ":" in name:
        raise RenderError(
            f"Caption file for burn-in must be a single name (no path separators): {name!r}"
        )
    return name.replace("'", r"\'")


def build_burnin_video_filter(
    encode_profile: EncodeProfile,
    *,
    subtitle_style: SubtitleStyle,
    captions_srt: Path,
    subtitle_font_size: int | None = None,
) -> str:
    """Concatenate geometry filter + subtitles burn-in using ``force_style`` from config.

    The SRT path must refer to a file that will exist under FFmpeg's working directory
    (see :func:`write_render_artifact`); only the basename is passed to ``subtitles=``.
    """
    if not captions_srt.is_file():
        raise RenderError(f"Caption file for burn-in not found: {captions_srt}")
    style = (
        replace(subtitle_style, font_size=subtitle_font_size)
        if subtitle_font_size is not None
        else subtitle_style
    )
    style = _scale_subtitle_style_for_ffmpeg_srt(style, encode_profile.height)
    sub_tok = _subtitles_srt_token(captions_srt.name)
    fs = _force_style_token_for_subtitles_filter(style)
    w = encode_profile.width
    h = encode_profile.height
    # Match libass layout to the frame *after* the geometry filter. Without this,
    # SRT→ASS defaults can scale Margins/Alignment as if the script were a different
    # resolution, so text appears mid-frame instead of bottom-center.
    return (
        f"{encode_profile.video_filter},subtitles={sub_tok}:force_style={fs}"
        f":original_size={w}x{h}"
    )


def _ffmpeg_has_subtitles_filter(ffmpeg_bin: str) -> bool:
    try:
        proc = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-h", "filter=subtitles"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as e:
        if e.errno == errno.ENOEXEC:
            raise RenderError(
                f"Cannot execute FFmpeg at {ffmpeg_bin!r} ({e}). "
                "That path is not a native binary for this machine (often a macOS build "
                "sitting in the repo root). Remove or rename it, point SOCIAL_CLIPR_FFMPEG "
                "at a Linux ffmpeg, or unset SOCIAL_CLIPR_FFMPEG to use `ffmpeg` on PATH."
            ) from e
        raise
    out = ((proc.stderr or "") + (proc.stdout or "")).lower()
    if "unknown filter" in out:
        return False
    return out.lstrip().startswith("filter subtitles")


def build_video_filter(
    encode_profile: EncodeProfile,
    *,
    subtitle_style: SubtitleStyle | None = None,
    captions_srt: Path | None = None,
    subtitle_font_size: int | None = None,
) -> str:
    """Full ``-vf`` chain: encode geometry, optional subtitle burn-in."""
    if (subtitle_style is None) ^ (captions_srt is None):
        raise ValueError(
            "subtitle_style and captions_srt must both be set or both omitted"
        )
    if subtitle_font_size is not None and (
        subtitle_style is None or captions_srt is None
    ):
        raise ValueError("subtitle_font_size requires subtitle_style and captions_srt")
    if subtitle_style is not None and captions_srt is not None:
        return build_burnin_video_filter(
            encode_profile,
            subtitle_style=subtitle_style,
            captions_srt=captions_srt,
            subtitle_font_size=subtitle_font_size,
        )
    return encode_profile.video_filter


def build_ffmpeg_command(
    ffmpeg_bin: str,
    *,
    input_path: Path,
    output_path: Path,
    encode_profile: EncodeProfile,
    subtitle_style: SubtitleStyle | None = None,
    captions_srt: Path | None = None,
    subtitle_font_size: int | None = None,
) -> list[str]:
    """Build the ffmpeg argv used for a real encode (tests assert this matches the profile)."""
    vf = build_video_filter(
        encode_profile,
        subtitle_style=subtitle_style,
        captions_srt=captions_srt,
        subtitle_font_size=subtitle_font_size,
    )
    return [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-vf",
        vf,
        "-r",
        str(encode_profile.frame_rate),
        "-c:v",
        encode_profile.video_codec,
        "-crf",
        str(encode_profile.crf),
        "-preset",
        encode_profile.encoder_preset,
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        encode_profile.audio_codec,
        "-b:a",
        f"{encode_profile.audio_bitrate_kbps}k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def write_render_artifact(
    input_path: Path,
    encode_profile: EncodeProfile,
    *,
    subtitle_style: SubtitleStyle | None = None,
    captions_srt: Path | None = None,
    subtitle_font_size: int | None = None,
    output_root: Path | None = None,
) -> Path:
    """Produce a profile-specific output mp4 under outputs/<stem>/.

    When ``subtitle_style`` and ``captions_srt`` are set and this is not a stub
    render, FFmpeg burns subtitles using the style (``force_style`` / libass).

    Set env ``SOCIAL_CLIPR_RENDER=stub`` to copy the input (no transcode or burn-in).
    """
    root = output_root or Path("outputs")
    job_dir = root / input_path.stem
    job_dir.mkdir(parents=True, exist_ok=True)
    pid = encode_profile.id
    output_path = job_dir / rendered_video_filename(pid)

    if os.environ.get("SOCIAL_CLIPR_RENDER", "").strip().lower() == "stub":
        shutil.copy2(input_path, output_path)
        return output_path

    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        if os.environ.get("SOCIAL_CLIPR_FFMPEG", "").strip():
            raise RenderError(
                "SOCIAL_CLIPR_FFMPEG is set but does not resolve to an ffmpeg executable "
                "(path must exist, or use a name found on PATH). "
                "Unset it to use `ffmpeg` on PATH, or set SOCIAL_CLIPR_RENDER=stub."
            )
        raise RenderError(
            "ffmpeg was not found on PATH. Install FFmpeg (e.g. `brew install ffmpeg`) "
            f"to produce a real {encode_profile.width}×{encode_profile.height} encode, "
            "or set SOCIAL_CLIPR_RENDER=stub to copy the input file only (no transcode). "
            "Optional: set SOCIAL_CLIPR_FFMPEG to an absolute ffmpeg path or a name on PATH."
        )
    if subtitle_style is not None and captions_srt is not None:
        if not _ffmpeg_has_subtitles_filter(ffmpeg):
            raise RenderError(
                f"This FFmpeg binary has no `subtitles` filter (needs libass): {ffmpeg}\n"
                "If you have several FFmpeg installs, point Social-CLIpper at the full build: "
                "export SOCIAL_CLIPR_FFMPEG=/absolute/path/to/ffmpeg "
                "(check candidates with e.g. `ffmpeg -hide_banner -h filter=subtitles`). "
                "On macOS, Homebrew's formula is often enough after `brew reinstall ffmpeg`; "
                "otherwise use SOCIAL_CLIPR_RENDER=stub to skip transcode."
            )
        dest_srt = job_dir / captions_srt.name
        if captions_srt.resolve() != dest_srt.resolve():
            shutil.copy2(captions_srt, dest_srt)
        captions_srt = dest_srt

    cmd = build_ffmpeg_command(
        ffmpeg,
        input_path=input_path.resolve(),
        output_path=output_path.resolve(),
        encode_profile=encode_profile,
        subtitle_style=subtitle_style,
        captions_srt=captions_srt,
        subtitle_font_size=subtitle_font_size,
    )
    burnin_cwd = (
        str(job_dir.resolve())
        if subtitle_style is not None and captions_srt is not None
        else None
    )
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
        cwd=burnin_cwd,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        rc = proc.returncode
        if rc == -9:
            hint = (
                " SIGKILL (-9): on Linux this is usually the OOM killer (ran out of RAM). "
                "Give the dev container or VM more memory, or try a shorter clip / fewer cues; "
                "subtitle burn-in can spike usage. Or set SOCIAL_CLIPR_RENDER=stub to skip FFmpeg."
            )
        elif rc is not None and rc < 0:
            hint = f" Process was killed by signal {-rc}."
        else:
            hint = ""
        raise RenderError(
            (
                f"ffmpeg failed (exit {rc}).{hint} {err[:800]}"
                if err
                else f"ffmpeg failed (exit {rc}).{hint}"
            ).rstrip()
        )
    return output_path
