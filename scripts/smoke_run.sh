#!/usr/bin/env bash
# End-to-end smoke: run the full pipeline and verify the job bundle under outputs/<stem>/.
#
# -----------------------------------------------------------------------------
# Quick mode (default) — CI-safe, no FFmpeg / Whisper required
# -----------------------------------------------------------------------------
#   • Exports SOCIAL_CLIPR_RENDER=stub and SOCIAL_CLIPR_TRANSCRIBE=stub
#   • Uses a tiny non-empty fake “.mp4” (not a valid media file; stubs skip decode)
#   • Verifies all canonical bundle files exist (see social_clipr.bundle)
#
# -----------------------------------------------------------------------------
# Real media mode — local validation of FFmpeg encode + burn-in
# -----------------------------------------------------------------------------
#   Set:  SOCIAL_CLIPR_SMOKE_REAL=1
#   Requires: ffmpeg on PATH
#   • Builds a short synthetic H.264+AAC clip (lavfi testsrc + anullsrc)
#   • Does NOT set stub env vars → real transcode + subtitle burn-in
#   • Transcription follows configs/stt.json (default whisper_cli); if `whisper`
#     is missing, the pipeline falls back to the deterministic stub transcript
#     (no large model download in CI when you only set REAL=1).
#   • After success, asserts run_summary.json bundle.render_mode == "ffmpeg" and
#     video_includes_burned_subtitles == true
#
# -----------------------------------------------------------------------------
# Optional Whisper strict check (only with REAL mode)
# -----------------------------------------------------------------------------
#   Set:  SOCIAL_CLIPR_SMOKE_WHISPER=1  (with SOCIAL_CLIPR_SMOKE_REAL=1)
#   Requires: `whisper` on PATH (e.g. pip install openai-whisper)
#   • Exits early with a clear message if Whisper is not installed — use this
#     locally when you want to prove the Whisper CLI path, not in default CI.
#
# Interpreter: set PYTHON to pin (e.g. PYTHON=.venv/bin/python bash scripts/smoke_run.sh)

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WORKDIR="$(mktemp -d)"
cleanup() {
  rm -rf "$WORKDIR"
}
trap cleanup EXIT

STEM="smoke-run-$$"
MP4="$WORKDIR/${STEM}.mp4"

REAL="${SOCIAL_CLIPR_SMOKE_REAL:-}"
WHISPER_STRICT="${SOCIAL_CLIPR_SMOKE_WHISPER:-}"

if [[ "$REAL" == "1" ]]; then
  if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "smoke_run: SOCIAL_CLIPR_SMOKE_REAL=1 requires ffmpeg on PATH" >&2
    exit 1
  fi
  if [[ "$WHISPER_STRICT" == "1" ]]; then
    if ! command -v whisper >/dev/null 2>&1; then
      echo "smoke_run: SOCIAL_CLIPR_SMOKE_WHISPER=1 requires the whisper CLI on PATH (e.g. pip install openai-whisper)." >&2
      exit 1
    fi
  fi
  unset SOCIAL_CLIPR_RENDER || true
  unset SOCIAL_CLIPR_TRANSCRIBE || true
  ffmpeg -hide_banner -loglevel error -y \
    -f lavfi -i "testsrc=duration=0.35:size=640x360:rate=30" \
    -f lavfi -i "anullsrc=r=48000:cl=stereo" \
    -shortest \
    -c:v libx264 \
    -pix_fmt yuv420p \
    -c:a aac \
    "$MP4"
else
  export SOCIAL_CLIPR_RENDER=stub
  export SOCIAL_CLIPR_TRANSCRIBE=stub
  printf 'x' >"$MP4"
fi

if [[ -n "${PYTHON:-}" ]]; then
  PY=("$PYTHON")
elif command -v python3 >/dev/null 2>&1; then
  PY=(python3)
elif command -v python >/dev/null 2>&1; then
  PY=(python)
else
  echo "smoke_run: set PYTHON or install python3 on PATH" >&2
  exit 1
fi

"${PY[@]}" -m social_clipr run --input "$MP4" --profile shorts-vertical

OUT="$ROOT/outputs/$STEM"
for f in \
  transcript.json \
  transcript.txt \
  captions.srt \
  captions.vtt \
  rendered-shorts-vertical.mp4 \
  run_summary.json \
  metadata_draft.json; do
  if [[ ! -f "$OUT/$f" ]]; then
    echo "smoke_run: missing expected file: $OUT/$f" >&2
    exit 1
  fi
done

if [[ "$REAL" == "1" ]]; then
  export SMOKE_RUN_SUMMARY_JSON="$OUT/run_summary.json"
  if ! "${PY[@]}" -c "
import json
import os
p = os.environ['SMOKE_RUN_SUMMARY_JSON']
d = json.load(open(p, encoding='utf-8'))
assert d.get('bundle', {}).get('render_mode') == 'ffmpeg', d
assert d.get('bundle', {}).get('video_includes_burned_subtitles') is True, d
"; then
    echo "smoke_run: run_summary bundle check failed (expected ffmpeg + burned subtitles)" >&2
    exit 1
  fi
  unset SMOKE_RUN_SUMMARY_JSON
fi

echo "smoke_run: ok ($OUT)${REAL:+ [SOCIAL_CLIPR_SMOKE_REAL=1]}"
rm -rf "$OUT"
