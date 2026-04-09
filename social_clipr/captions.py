"""Caption file generation (.srt and .vtt) from transcript JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from social_clipr.bundle import CAPTIONS_SRT_NAME, CAPTIONS_VTT_NAME
from social_clipr.word_cues import normalize_word_cues


def _format_srt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def _format_vtt_time(seconds: float) -> str:
    millis = int(round(seconds * 1000))
    hours, rem = divmod(millis, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02}.{ms:03}"


def write_caption_artifacts(
    transcript_json_path: Path,
    *,
    ignore_stored_word_cues: bool = False,
) -> dict[str, Path]:
    payload = cast(
        dict[str, object],
        json.loads(transcript_json_path.read_text(encoding="utf-8")),
    )
    if ignore_stored_word_cues:
        payload = dict(payload)
        payload["word_cues"] = []
    cues = normalize_word_cues(payload)
    base_dir = transcript_json_path.parent

    srt_path = base_dir / CAPTIONS_SRT_NAME
    vtt_path = base_dir / CAPTIONS_VTT_NAME

    srt_blocks: list[str] = []
    vtt_lines: list[str] = ["WEBVTT", ""]

    for idx, cue in enumerate(cues, start=1):
        start = float(cue.start)
        end = float(cue.end)
        text = cue.text

        srt_blocks.append(
            f"{idx}\n"
            f"{_format_srt_time(start)} --> {_format_srt_time(end)}\n"
            f"{text}\n"
        )
        vtt_lines.append(f"{_format_vtt_time(start)} --> {_format_vtt_time(end)}")
        vtt_lines.append(text)
        vtt_lines.append("")

    srt_path.write_text("\n".join(srt_blocks), encoding="utf-8")
    vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")

    return {"srt": srt_path, "vtt": vtt_path}
