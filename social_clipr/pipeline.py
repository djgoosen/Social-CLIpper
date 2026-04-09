"""End-to-end pipeline orchestration (ingest → package)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

from social_clipr.captions import write_caption_artifacts
from social_clipr.config_loader import (
    PipelineConfig,
    require_encode_profile,
    require_subtitle_style,
)
from social_clipr.ingest import IngestValidationError, validate_input_mp4
from social_clipr.package import write_metadata_draft, write_run_summary
from social_clipr.render import RenderError, write_render_artifact
from social_clipr.transcribe import write_transcript_artifacts
from social_clipr.transcript_resume import (
    TranscriptResumeError,
    apply_refresh_word_cues_to_file,
    ensure_transcript_txt,
    resolve_transcript_json_for_resume,
)
from social_clipr.word_cues import count_stored_word_cues, normalize_word_cues


def validate_subtitle_font_size(n: int) -> None:
    """Reject unusable font sizes before render (matches subtitle style preset minimum)."""
    if n < 8:
        raise ValueError("Subtitle font size must be at least 8.")
    if n > 512:
        raise ValueError("Subtitle font size must be at most 512.")


def subtitle_font_size_from_environment() -> int | None:
    """Parse ``SOCIAL_CLIPR_SUBTITLE_FONT_SIZE`` if set; raise :class:`ValueError` if invalid."""
    raw = os.environ.get("SOCIAL_CLIPR_SUBTITLE_FONT_SIZE", "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
    except ValueError as exc:
        raise ValueError(
            f"SOCIAL_CLIPR_SUBTITLE_FONT_SIZE must be an integer; got {raw!r}"
        ) from exc
    validate_subtitle_font_size(n)
    return n


def run_social_clipr_job(
    input_path_str: str,
    profile: str,
    *,
    pipeline_config: PipelineConfig,
    subtitle_style: str = "minimal",
    job_preset: str | None = None,
    subtitle_font_size: int | None = None,
    skip_transcribe: bool = False,
    refresh_word_cues_from_segments: bool = False,
    captions_from_segments: bool = False,
    output_root: Path | None = None,
    log: Callable[[str], None] = print,
) -> int:
    """Run all pipeline stages in order. Returns 0 on success, 2 on ingest failure."""
    if subtitle_font_size is not None:
        try:
            validate_subtitle_font_size(subtitle_font_size)
        except ValueError as exc:
            log(f"Config error: {exc}")
            return 2

    log("[pipeline] 1/5 ingest: validating input")
    try:
        input_path = validate_input_mp4(input_path_str)
    except IngestValidationError as exc:
        log(f"Ingest validation error: {exc}")
        return 2
    log(f"[pipeline] 1/5 ingest: ok ({input_path})")

    if skip_transcribe:
        log("[pipeline] 2/5 transcribe: skipped (existing transcript.json)")
        try:
            transcript_json_path = resolve_transcript_json_for_resume(
                input_path, output_root=output_root
            )
        except TranscriptResumeError as exc:
            log(f"Transcript resume error: {exc}")
            return 2
        artifacts = {
            "json": transcript_json_path,
            "txt": ensure_transcript_txt(transcript_json_path),
        }
        log(f"[pipeline] 2/5 transcribe: using {artifacts['json']}")
    else:
        log("[pipeline] 2/5 transcribe: generating transcript")
        artifacts = write_transcript_artifacts(
            input_path,
            pipeline_config,
            output_root=output_root,
            log=log,
        )
        log(f"[pipeline] 2/5 transcribe: ok ({artifacts['json']})")

    if refresh_word_cues_from_segments:
        log("[pipeline] 2b: refreshing word_cues from segments")
        apply_refresh_word_cues_to_file(artifacts["json"])

    log("[pipeline] 3/5 captions: writing SRT/VTT")
    transcript_payload = json.loads(artifacts["json"].read_text(encoding="utf-8"))
    n_stored = count_stored_word_cues(transcript_payload)
    eff_payload: dict[str, object] = dict(transcript_payload)
    if captions_from_segments:
        eff_payload["word_cues"] = []
    preview_cues = normalize_word_cues(eff_payload)
    if captions_from_segments and n_stored > 0:
        log(
            f"[pipeline] captions: ignoring {n_stored} stored word_cue(s) "
            f"(--captions-from-segments); using segments only → {len(preview_cues)} cue(s)"
        )
    elif n_stored > 0:
        log(
            f"[pipeline] captions: using stored word_cues ({n_stored} in JSON) → "
            f"{len(preview_cues)} SRT/VTT line(s); segment text does not drive timing"
        )
    else:
        log(
            f"[pipeline] captions: no usable word_cues in JSON → "
            f"{len(preview_cues)} cue(s) derived from segments"
        )

    caption_artifacts = write_caption_artifacts(
        artifacts["json"],
        ignore_stored_word_cues=captions_from_segments,
    )
    log(
        f"[pipeline] 3/5 captions: ok ({caption_artifacts['srt']}, {caption_artifacts['vtt']})"
    )

    encode = require_encode_profile(pipeline_config, profile)
    sub_style = require_subtitle_style(pipeline_config, subtitle_style)
    log(
        f"[pipeline] 4/5 render: profile={profile}, subtitle_style={subtitle_style}"
        + (
            f", subtitle_font_size={subtitle_font_size}"
            if subtitle_font_size is not None
            else ""
        )
        + f" (config from {pipeline_config.config_dir})"
    )
    render_stub = os.environ.get("SOCIAL_CLIPR_RENDER", "").strip().lower() == "stub"
    if render_stub:
        log(
            "[pipeline] 4/5 render: SOCIAL_CLIPR_RENDER=stub — copying input to "
            "rendered mp4 without FFmpeg burn-in (captions.srt is still written)"
        )
    try:
        rendered_mp4 = write_render_artifact(
            input_path,
            encode,
            subtitle_style=sub_style,
            captions_srt=caption_artifacts["srt"],
            subtitle_font_size=subtitle_font_size,
            output_root=output_root,
        )
    except RenderError as exc:
        log(f"Render error: {exc}")
        return 2
    log(f"[pipeline] 4/5 render: ok ({rendered_mp4})")

    subtitle_font_size_effective = (
        subtitle_font_size if subtitle_font_size is not None else sub_style.font_size
    )

    log("[pipeline] 5/5 package: run summary and metadata")
    root = Path("outputs") if output_root is None else output_root
    job_dir = root / input_path.stem
    render_mode = "stub_copy" if render_stub else "ffmpeg"
    transcript_source = "resumed_from_disk" if skip_transcribe else None
    summary_path = write_run_summary(
        job_dir,
        profile=profile,
        subtitle_style=subtitle_style,
        subtitle_font_size_effective=subtitle_font_size_effective,
        source_input=input_path,
        transcript_json=artifacts["json"],
        transcript_txt=artifacts["txt"],
        captions_srt=caption_artifacts["srt"],
        captions_vtt=caption_artifacts["vtt"],
        rendered_mp4=rendered_mp4,
        render_mode=render_mode,
        job_preset=job_preset,
        transcript_source=transcript_source,
    )
    metadata_path = write_metadata_draft(
        job_dir,
        stem=input_path.stem,
        encode_profile_id=profile,
        subtitle_style_id=subtitle_style,
        subtitle_font_size_effective=subtitle_font_size_effective,
        source_filename=input_path.name,
        render_mode=render_mode,
        job_preset=job_preset,
        transcript_source=transcript_source,
    )
    log(f"[pipeline] 5/5 package: ok ({summary_path}, {metadata_path})")

    log("[pipeline] complete: all stages finished")
    log(f"Transcript JSON: {artifacts['json']}")
    log(f"Transcript TXT: {artifacts['txt']}")
    log(f"Captions SRT: {caption_artifacts['srt']}")
    log(f"Captions VTT: {caption_artifacts['vtt']}")
    log(f"Rendered MP4: {rendered_mp4}")
    log(f"Run summary: {summary_path}")
    log(f"Metadata draft: {metadata_path}")
    return 0
