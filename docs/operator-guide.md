# Operator guide — configs, encode, burn-in (Sprint 2 + Sprint 3)

All commands below assume the **repository root** (`social-clipr/`, where `pyproject.toml`, `configs/`, and `social_clipr/` live). Use relative paths as shown, or substitute absolute paths.

## What you need

| Tool | When |
|------|------|
| **Python 3.10+** | Always |
| **`ffmpeg`** on `PATH` | Real encode and subtitle **burn-in** (not needed if you set `SOCIAL_CLIPR_RENDER=stub`) |
| **`SOCIAL_CLIPR_FFMPEG`** (optional) | Pin a specific **ffmpeg** binary: absolute path to the executable, or a name found on `PATH` (useful when multiple installs exist or CI pins a known build). Ignored when **`SOCIAL_CLIPR_RENDER=stub`**. |
| **`whisper`** CLI (optional) | Real speech-to-text per `configs/stt.json` when `engine` is `whisper_cli` — e.g. `pip install openai-whisper` and ensure `whisper` is on `PATH` |
| **`faster-whisper`** (optional) | Only if `configs/stt.json` sets `"engine": "faster_whisper"` — `pip install faster-whisper` (local CPU; no API) |

Bundled fonts for burn-in use **Arial** / **Arial Black** in the sample `configs/subtitle_styles/*.json`. On **macOS** these usually exist; on **Linux** you may switch `font_family` to something installed (e.g. **DejaVu Sans**) in your own preset JSON.

## One-time setup (from repo root)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Shipped config examples (edit copies or use `--config-dir`)

### Encode profiles (`configs/encode/*.json`)

| File | Role |
|------|------|
| `configs/encode/shorts-vertical.json` | **1080×1920** vertical: **center-crop** landscape to fill the frame (classic shorts look; sides of wide screen recordings are cropped). |
| `configs/encode/shorts-vertical-fit.json` | **1080×1920** vertical: **letterbox** — full landscape frame scaled to fit with bars (good for **MacBook / screen recordings** where you want the whole capture visible). |
| `configs/encode/youtube-horizontal.json` | **1920×1080** horizontal: letterbox to 16:9 (laptop / YouTube-style landscape export). |

All use H.264 + AAC with CRF and frame rate from JSON. The loader requires `video_filter` to **prove** output size using **`crop=W:H`**, **`pad=W:H`**, or (if there is no crop/pad in the chain) **`scale=W:H`** — see the main [README](../README.md#configuration).

### Subtitle styles (`configs/subtitle_styles/*.json`)

| File | Role |
|------|------|
| `configs/subtitle_styles/minimal.json` | Default burn-in style (`--subtitle-style minimal`). Bundled **`font_size`** is tuned for **1080×1920** readability. |
| `configs/subtitle_styles/bold_social.json` | Alternate style (`--subtitle-style bold_social`), larger than **minimal** for contrast. |
| `configs/subtitle_styles/purple_lower_third.json` | Lower-center (**`alignment` 2**, **`margin_v` 160**) purple **`primary_color`** for one-word cue burn-in (`--subtitle-style purple_lower_third`). |

### Custom font family and primary color (copy/paste presets)

Use a small **`--config-dir`** tree with **`encode/`**, **`subtitle_styles/`** (≥ **two** JSON files; **`id`** = filename stem), and **`stt.json`**. Pick the active burn-in preset with **`run --subtitle-style <id>`**.

**Example A — serif `font_family`:** `subtitle_styles/serif_brand.json`

```json
{
  "id": "serif_brand",
  "font_family": "Georgia",
  "font_size": 38,
  "primary_color": "&HFFFFFF&",
  "outline_color": "&H000000&",
  "outline_width": 2,
  "margin_v": 160,
  "alignment": 2
}
```

**Example B — green `primary_color`:** `subtitle_styles/high_visibility.json`

```json
{
  "id": "high_visibility",
  "font_family": "Arial",
  "font_size": 40,
  "primary_color": "&H0000FF00&",
  "outline_color": "&H000000&",
  "outline_width": 3,
  "margin_v": 160,
  "alignment": 2
}
```

Runnable pattern (after copying static **`configs/stt.json`** and **`encode/shorts-vertical.json`**, plus **`minimal.json`** under **`subtitle_styles/`** for the second required style):

```bash
python3 -m social_clipr run \
  --input ./your-video.mp4 \
  --profile shorts-vertical \
  --subtitle-style high_visibility \
  --config-dir ./operator-styles
```

Full **`mkdir` / `cp`** walkthrough and ASS color notes: main [README § Custom subtitle styles](../README.md#configuration).

### Other

| File | Role |
|------|------|
| `configs/stt.json` | `engine` (`stub` \| `whisper_cli` \| `faster_whisper`), `model`, `language` |

See `social_clipr.bundle` for canonical output filenames (`rendered-<encode_profile_id>.mp4`).

## Sprint 3 — Choosing a profile (especially laptop / QuickTime)

- **True 9:16 shorts, content can be cropped:** `--profile shorts-vertical`
- **Landscape or 16:10 screen capture, keep the full rectangle in 9:16 with bars:** `--profile shorts-vertical-fit`
- **16:9 landscape deliverable (e.g. YouTube main):** `--profile youtube-horizontal`

Example (letterboxed vertical from a wide recording):

```bash
python3 -m social_clipr run \
  --input ./screen-recording.mp4 \
  --profile shorts-vertical-fit \
  --subtitle-style minimal
```

## Subtitle font size (CLI, preset, env)

**Precedence for `run`:** `--subtitle-font-size` → job preset field **`subtitle_font_size`** → **`SOCIAL_CLIPR_SUBTITLE_FONT_SIZE`** → the style JSON **`font_size`** (`minimal` / `bold_social` defaults).

- CLI: `run --subtitle-font-size 48`
- Preset JSON: optional integer **`subtitle_font_size`** (8–512), or save with  
  `preset save ... --subtitle-font-size 48`
- Env: `export SOCIAL_CLIPR_SUBTITLE_FONT_SIZE=48`

**`run_summary.json`** and **`metadata_draft.json`** include **`subtitle_font_size`** (resolved value used for burn-in intent).

## Happy path 1 — Full pipeline without FFmpeg (CI-style)

Uses stub transcript and copies the input for “render” (no transcode, **no** burn-in).

```bash
export SOCIAL_CLIPR_TRANSCRIBE=stub
export SOCIAL_CLIPR_RENDER=stub
python3 -m social_clipr run --input ./your-video.mp4 --profile shorts-vertical
```

Artifacts appear under `outputs/<basename-without-.mp4>/` (see main [README](../README.md#output-layout)).

## Happy path 2 — Real vertical encode + burned subtitles

Requires a working **ffmpeg** (or set **`SOCIAL_CLIPR_FFMPEG`**). Do **not** set `SOCIAL_CLIPR_RENDER=stub`.

```bash
unset SOCIAL_CLIPR_RENDER SOCIAL_CLIPR_TRANSCRIBE
python3 -m social_clipr run \
  --input ./your-video.mp4 \
  --profile shorts-vertical \
  --subtitle-style minimal
```

Optional: pin ffmpeg (Homebrew Cellar path example — adjust for your machine):

```bash
export SOCIAL_CLIPR_FFMPEG=/opt/homebrew/bin/ffmpeg
python3 -m social_clipr run --input ./your-video.mp4 --profile shorts-vertical-fit
```

Try the other bundled preset:

```bash
python3 -m social_clipr run --input ./your-video.mp4 --profile shorts-vertical --subtitle-style bold_social
```

Confirm **`run_summary.json`** → **`bundle.video_includes_burned_subtitles`** is **true** and **`bundle.render_mode`** is **`ffmpeg`**.

## Happy path 3 — Optional real smoke (synthetic clip)

From repo root, exercises **real** encode + burn-in without supplying your own media:

```bash
SOCIAL_CLIPR_SMOKE_REAL=1 PYTHON=.venv/bin/python bash scripts/smoke_run.sh
```

See `scripts/smoke_run.sh` for **quick** vs **real** vs optional **Whisper strict** modes.

## Happy path 4 — Whisper CLI transcription

1. Install Whisper and ensure `whisper` is on `PATH`.
2. Keep **`configs/stt.json`** with `"engine": "whisper_cli"` and a small **`model`** (e.g. `tiny`) for first runs.
3. Run **without** `SOCIAL_CLIPR_TRANSCRIBE=stub`:

```bash
unset SOCIAL_CLIPR_TRANSCRIBE
python3 -m social_clipr run --input ./your-video.mp4 --profile shorts-vertical
```

If Whisper fails or is missing, the pipeline **falls back** to the deterministic stub and logs the reason (no multi-gigabyte download is required for the default **pytest** suite).

## Job presets (save and reuse)

Write a small JSON file that pins **encode profile**, **subtitle style**, optional **`config_dir`**, and optional **`subtitle_font_size`**. Then run with **`--preset`**; **`--profile`**, **`--subtitle-style`**, **`--subtitle-font-size`**, and **`--config-dir`** on the CLI override the preset when you pass them.

```bash
python3 -m social_clipr preset save \
  --profile shorts-vertical \
  --subtitle-style bold_social \
  --subtitle-font-size 40 \
  --config-dir ./configs \
  -o ./my-clipr-job.json

python3 -m social_clipr run --input ./your-video.mp4 --preset ./my-clipr-job.json
```

When **`--preset`** is used, **`run_summary.json`** and **`metadata_draft.json`** include **`job_preset`** (absolute path to the file).

## Custom config tree

```bash
python3 -m social_clipr run \
  --config-dir ./my-configs \
  --input ./your-video.mp4 \
  --profile <encode-profile-id>
```

`my-configs/` must contain `encode/`, `subtitle_styles/`, and `stt.json` with the same rules as `configs/`.

## Transcript polish without re-running STT (Sprint 5)

After a full **`run`**, you can edit **`outputs/<stem>/transcript.json`**, then regenerate captions and the rendered video **without** calling Whisper again.

1. **Layout** — The job folder name must match the **basename** of your **`--input`** file (e.g. `clip.mp4` → `outputs/clip/transcript.json`).
2. **`word_cues` vs `segments`** — Caption generation uses **`word_cues`** when that array is **non-empty** (one word per cue). If you only edit **`segments[].text`**, either clear **`word_cues`** (so timing is rebuilt from segments) or update **`word_cues`** to stay consistent.

   **If you edited `segments` only** (common gotcha): use **`--refresh-word-cues-from-segments`** (persists new **`word_cues`** into **`transcript.json`**) or **`--captions-from-segments`** (this run only; does not edit JSON), or set **`word_cues`** to **`[]`** in the file. Otherwise on-screen wording/timing still follows the old **`word_cues`** list.

3. **`--skip-transcribe`** — Ingest still validates the same **`.mp4`** path, then the pipeline loads **`transcript.json`**, writes **`captions.srt` / `captions.vtt`**, runs **render** and **package**. **`run_summary.json`** includes **`transcript_source`: `resumed_from_disk`** and **`transcribe_skipped`: true** when you used skip mode.
4. **`--refresh-word-cues-from-segments`** — Optional. Rebuilds **`word_cues`** from **`segments`** only and **rewrites** **`transcript.json`** on disk before captions. Use this after segment-only edits when you want deterministic word splitting without hand-editing **`word_cues`**.
5. **`--captions-from-segments`** — Optional. For **this run only**, ignore stored **`word_cues`** and build **`.srt` / `.vtt`** from **`segments`** (does not modify **`transcript.json`**). Pair with **`--skip-transcribe`** when you resumed from disk and want segment-driven captions without editing the JSON.

**Checking what the pipeline did** — Console logs include a **`[pipeline] captions:`** line: whether stored **`word_cues`** were used, ignored, or cues were derived from **`segments`**, and how many cues were written. If the **`.mp4`** shows no burned-in text, confirm **`SOCIAL_CLIPR_RENDER`** is **not** **`stub`** (stub copies the input and skips FFmpeg burn-in; **`captions.srt`** is still written). Open **`outputs/<stem>/captions.srt`** to verify timing and text.

Example (stub render/transcribe for a quick local check):

```bash
export SOCIAL_CLIPR_RENDER=stub
export SOCIAL_CLIPR_TRANSCRIBE=stub
python3 -m social_clipr run --input ./clip.mp4 --profile shorts-vertical
# edit outputs/clip/transcript.json
python3 -m social_clipr run --input ./clip.mp4 --profile shorts-vertical --skip-transcribe
# optional: rebuild word cues from segments, then captions + render
python3 -m social_clipr run --input ./clip.mp4 --profile shorts-vertical \
  --skip-transcribe --refresh-word-cues-from-segments

# segment-only edit, one-shot captions from segments without rewriting transcript.json:
python3 -m social_clipr run --input ./clip.mp4 --profile shorts-vertical \
  --skip-transcribe --captions-from-segments
```

## Further reading

- [README.md](../README.md) — CLI flags, environment variables, exit codes