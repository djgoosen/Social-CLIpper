"""Transcription: config-driven stub, OpenAI Whisper CLI, or faster-whisper (optional)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from social_clipr.bundle import TRANSCRIPT_JSON_NAME, TRANSCRIPT_TXT_NAME
from social_clipr.config_loader import PipelineConfig, SpeechToTextConfig
from social_clipr.word_cues import normalize_word_cues, serialize_word_cues


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


def _deterministic_segments(input_path: Path) -> list[TranscriptSegment]:
    digest = hashlib.sha256(str(input_path.resolve()).encode("utf-8")).hexdigest()
    seed = int(digest[:8], 16)
    topic = [
        "welcome to social clipr",
        "this transcript is deterministic",
        "pipeline stages are being scaffolded",
    ]
    idx = seed % len(topic)
    return [
        TranscriptSegment(start=0.0, end=2.5, text=topic[idx]),
        TranscriptSegment(start=2.5, end=5.0, text=topic[(idx + 1) % len(topic)]),
    ]


def _segment_rows_from_transcript_segments(
    segments: list[TranscriptSegment],
) -> list[dict[str, Any]]:
    """Plain segment rows with no per-word timings (fallback split in normalize_word_cues)."""
    return [{"start": s.start, "end": s.end, "text": s.text} for s in segments]


def _write_payload(
    job_dir: Path,
    input_path: Path,
    segment_rows: list[dict[str, Any]],
    *,
    engine: str,
) -> dict[str, Path]:
    transcript_json = job_dir / TRANSCRIPT_JSON_NAME
    transcript_txt = job_dir / TRANSCRIPT_TXT_NAME
    normalized_payload: dict[str, object] = {"segments": segment_rows}
    word_cues = normalize_word_cues(normalized_payload)
    payload = {
        "source": str(input_path),
        "segment_count": len(segment_rows),
        "segments": segment_rows,
        "word_cue_count": len(word_cues),
        "word_cues": serialize_word_cues(word_cues),
        "engine": engine,
    }
    transcript_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    transcript_txt.write_text(
        "\n".join(str(row.get("text", "")).strip() for row in segment_rows) + "\n",
        encoding="utf-8",
    )
    return {"json": transcript_json, "txt": transcript_txt}


def _effective_whisper_params(stt: SpeechToTextConfig) -> tuple[str, str | None]:
    """Env overrides config for developer workflows (CI still uses config or stub env)."""
    model = os.environ.get("SOCIAL_CLIPR_WHISPER_MODEL", "").strip() or stt.model
    env_lang = os.environ.get("SOCIAL_CLIPR_WHISPER_LANGUAGE")
    if env_lang is not None:
        language = env_lang.strip() or None
    else:
        language = stt.language.strip() or None
    return model, language


def _segment_dicts_from_whisper_json(data: dict[str, object]) -> list[dict[str, Any]]:
    """Parse OpenAI Whisper JSON: keep segment text and optional per-word timings."""
    raw = data.get("segments") or []
    rows: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return rows
    for seg in raw:
        if not isinstance(seg, dict):
            continue
        try:
            start = float(seg["start"])
            end = float(seg["end"])
            text = str(seg.get("text", "")).strip()
        except (KeyError, TypeError, ValueError):
            continue
        row: dict[str, Any] = {"start": start, "end": end, "text": text}
        raw_words = seg.get("words")
        if isinstance(raw_words, list):
            words_out: list[dict[str, Any]] = []
            for w in raw_words:
                if not isinstance(w, dict):
                    continue
                try:
                    wtext = str(w.get("text", w.get("word", "")) or "").strip()
                    if not wtext:
                        continue
                    words_out.append(
                        {
                            "start": float(w["start"]),
                            "end": float(w["end"]),
                            "text": wtext,
                        }
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            if words_out:
                row["words"] = words_out
        rows.append(row)
    return rows


def _path_looks_like_pyenv_shim(executable: str) -> bool:
    """True if *executable* is a pyenv (or pyenv-win) shim — often wrong Python for a venv."""
    p = Path(executable).resolve().as_posix().lower()
    return "pyenv" in p and "shim" in p


def _resolve_whisper_cli_prefix() -> tuple[list[str] | None, bool]:
    """Return (argv prefix for Whisper, skipped_pyenv_shim).

    Prefer ``python -m whisper`` when the package is importable in the current
    process. If the package is missing, do not run a pyenv ``whisper`` shim: it
    typically resolves to another Python version and exits 127 inside venvs.
    """
    if importlib.util.find_spec("whisper") is not None:
        return [sys.executable, "-m", "whisper"], False
    exe = shutil.which("whisper")
    if not exe:
        return None, False
    if _path_looks_like_pyenv_shim(exe):
        return None, True
    return [exe], False


def _try_whisper_cli(
    input_path: Path,
    job_dir: Path,
    *,
    model: str,
    language: str | None,
    log: Callable[[str], None] | None,
) -> dict[str, Path] | None:
    prefix, skipped_pyenv_shim = _resolve_whisper_cli_prefix()
    if not prefix:
        if skipped_pyenv_shim and log:
            log(
                "[pipeline] transcribe: ignoring pyenv `whisper` shim (openai-whisper "
                "is not installed for this interpreter); pip install openai-whisper "
                "in the active venv."
            )
        return None
    with tempfile.TemporaryDirectory(prefix="social-clipr-whisper-") as tmp:
        cmd = [
            *prefix,
            str(input_path),
            "--output_dir",
            tmp,
            "--output_format",
            "json",
            "--model",
            model,
        ]
        if language:
            cmd.extend(["--language", language])
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            if log:
                log(
                    f"[pipeline] transcribe: whisper failed ({proc.returncode}); "
                    f"using stub. {err[:300]}"
                )
            return None
        base = input_path.stem
        whisper_json = Path(tmp) / f"{base}.json"
        if not whisper_json.is_file():
            if log:
                log("[pipeline] transcribe: whisper produced no JSON; using stub.")
            return None
        data = cast(
            dict[str, object], json.loads(whisper_json.read_text(encoding="utf-8"))
        )
        segment_rows = _segment_dicts_from_whisper_json(data)
        if not segment_rows:
            if log:
                log("[pipeline] transcribe: whisper returned no segments; using stub.")
            return None
        if log:
            via = "python -m whisper" if len(prefix) > 1 else "whisper"
            log(
                f"[pipeline] transcribe: using whisper_cli ({via}, model={model}, "
                f"segments={len(segment_rows)})"
            )
        return _write_payload(
            job_dir, input_path, segment_rows, engine=f"whisper_cli:{model}"
        )


def _try_faster_whisper(
    input_path: Path,
    job_dir: Path,
    *,
    model: str,
    language: str | None,
    log: Callable[[str], None] | None,
) -> dict[str, Path] | None:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        if log:
            log(
                "[pipeline] transcribe: faster_whisper engine selected but "
                "the package is not installed (pip install faster-whisper); using stub."
            )
        return None
    try:
        wmodel = WhisperModel(model, device="cpu", compute_type="int8")
        segments_gen, _info = wmodel.transcribe(
            str(input_path),
            language=language,
            word_timestamps=True,
        )
        segment_rows: list[dict[str, Any]] = []
        for s in segments_gen:
            text = (s.text or "").strip()
            row: dict[str, Any] = {
                "start": float(s.start),
                "end": float(s.end),
                "text": text,
            }
            words_attr = getattr(s, "words", None)
            if words_attr:
                words_out: list[dict[str, Any]] = []
                for w in words_attr:
                    wtext = str(getattr(w, "word", "") or "").strip()
                    if not wtext:
                        continue
                    try:
                        words_out.append(
                            {
                                "start": float(w.start),
                                "end": float(w.end),
                                "text": wtext,
                            }
                        )
                    except (TypeError, ValueError):
                        continue
                if words_out:
                    row["words"] = words_out
            segment_rows.append(row)
        if not segment_rows:
            if log:
                log(
                    "[pipeline] transcribe: faster_whisper returned no segments; using stub."
                )
            return None
        if log:
            log(
                f"[pipeline] transcribe: using faster_whisper (model={model}, "
                f"segments={len(segment_rows)})"
            )
        return _write_payload(
            job_dir, input_path, segment_rows, engine=f"faster_whisper:{model}"
        )
    except (
        Exception
    ) as exc:  # noqa: BLE001 — surface any runtime/model error as stub fallback
        if log:
            log(
                f"[pipeline] transcribe: faster_whisper error ({type(exc).__name__}); "
                f"using stub. {exc!s}"[:400]
            )
        return None


def write_transcript_artifacts(
    input_path: Path,
    pipeline_config: PipelineConfig,
    output_root: Path | None = None,
    *,
    log: Callable[[str], None] | None = None,
) -> dict[str, Path]:
    root = output_root or Path("outputs")
    job_dir = root / input_path.stem
    job_dir.mkdir(parents=True, exist_ok=True)

    if os.environ.get("SOCIAL_CLIPR_TRANSCRIBE", "").strip().lower() == "stub":
        if log:
            log("[pipeline] transcribe: using stub (SOCIAL_CLIPR_TRANSCRIBE=stub)")
        segments = _deterministic_segments(input_path)
        return _write_payload(
            job_dir,
            input_path,
            _segment_rows_from_transcript_segments(segments),
            engine="stub",
        )

    stt = pipeline_config.stt
    if stt.engine == "stub":
        if log:
            log("[pipeline] transcribe: using stub (configs/stt.json engine=stub)")
        segments = _deterministic_segments(input_path)
        return _write_payload(
            job_dir,
            input_path,
            _segment_rows_from_transcript_segments(segments),
            engine="stub",
        )

    model, language = _effective_whisper_params(stt)

    if stt.engine == "whisper_cli":
        out = _try_whisper_cli(
            input_path, job_dir, model=model, language=language, log=log
        )
        if out is not None:
            return out
        if log:
            log(
                "[pipeline] transcribe: whisper CLI not found or failed; "
                "using deterministic stub. Install: pip install openai-whisper "
                "in this environment (the pipeline runs `python -m whisper` when "
                "the package is importable, else the `whisper` executable on PATH)."
            )
        segments = _deterministic_segments(input_path)
        return _write_payload(
            job_dir,
            input_path,
            _segment_rows_from_transcript_segments(segments),
            engine="stub",
        )

    if stt.engine == "faster_whisper":
        out = _try_faster_whisper(
            input_path, job_dir, model=model, language=language, log=log
        )
        if out is not None:
            return out
        segments = _deterministic_segments(input_path)
        return _write_payload(
            job_dir,
            input_path,
            _segment_rows_from_transcript_segments(segments),
            engine="stub",
        )

    segments = _deterministic_segments(input_path)
    return _write_payload(
        job_dir,
        input_path,
        _segment_rows_from_transcript_segments(segments),
        engine="stub",
    )
