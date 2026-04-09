# Social CLIpper

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE.md)
[![CI](https://github.com/djgoosen/Social-CLIpper/actions/workflows/ci.yml/badge.svg)](https://github.com/djgoosen/Social-CLIpper/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white)](https://docs.pytest.org/)
<!-- Private repo: Codecov badge needs ?token=… from Codecov → Settings → Badge (replace URL in the line below). -->
[![codecov](https://codecov.io/gh/djgoosen/Social-CLIpper/graph/badge.svg)](https://codecov.io/gh/djgoosen/Social-CLIpper)
[![Commit history](https://img.shields.io/badge/commits-history-181717?logo=github)](https://github.com/djgoosen/Social-CLIpper/commits/main)
[![Pylint](https://img.shields.io/badge/lint-pylint-ffc300?logo=python&logoColor=black)](https://pylint.pycqa.org/)

"Social CLIpper" (aka `social-clipr`) is a simple, 100% local, CLI-first pipeline that turns any local `.mp4` into a transcript, captions (`.srt` / `.vtt`), a rendered output video, and a run summary under `outputs/<video-stem>/`.

Recent example video: [Social CLIpper Example Video](https://youtu.be/xUkl7-e__z8)

## Requirements

- Python **3.10+**
- A virtual environment is recommended (see below).
- **FFmpeg** (`ffmpeg` on your `PATH` - the full FFmpeg package is required) for a **real** vertical re-encode on profile `shorts-vertical`. **Subtitle burn-in** needs a build that includes the **`subtitles`** filter (**libass**). Minimal or custom FFmpeg packages may omit it; Homebrew’s default **ffmpeg** formula usually includes libass. If burn-in is unavailable, the pipeline reports that clearly; use `SOCIAL_CLIPR_RENDER=stub` to skip transcode, or reinstall FFmpeg with libass enabled.
- **Optional:** [OpenAI Whisper](https://github.com/openai/whisper) CLI (`whisper` on your `PATH`, e.g. `pip install openai-whisper`) for **speech-to-text**. If Whisper is not available, the pipeline uses a **deterministic stub transcript** (not your audio) and logs that fact.

Encode settings (resolution, filter graph, codecs, CRF, audio) and **subtitle style presets** for future burn-in live under declarative JSON in **`configs/`** (see [Configuration](#configuration) below).

## Setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

To work without installing, ensure the project root is on `PYTHONPATH` (tests use `pyproject.toml` `pythonpath = ["."]`), or run with `pip install -e .`.

### Operator guide

Step-by-step workflows (encode profiles, laptop/QuickTime framing, subtitle font overrides, **`SOCIAL_CLIPR_FFMPEG`**, stub vs real FFmpeg, Whisper, smoke): **[docs/operator-guide.md](docs/operator-guide.md)**.

## Usage

### Help and version

```bash
python3 -m social_clipr --help
python3 -m social_clipr run --help
python3 -m social_clipr preset save --help
python3 -m social_clipr --version
```

If the package is installed, you can also use the `social-clipr` console script (same as `python -m social_clipr`).

### Run the full pipeline

**1080×1920 vertical (shorts-style center crop)** — typical phone/shorts deliverable; landscape sources are scaled and cropped to **1080×1920**:

```bash
source .venv/bin/activate
export SOCIAL_CLIPR_FFMPEG=$HOME/Downloads/ffmpeg
python3 -m social_clipr run --input /path/to/video.mp4 --profile shorts-vertical
```

For input `myclip.mp4`, FFmpeg (non-stub) writes **`outputs/myclip/rendered-shorts-vertical.mp4`** at **1080×1920** (see `configs/encode/shorts-vertical.json`).

**1080×1920 vertical (letterbox / laptop screen capture)** — full frame preserved with side bars:

```bash
export SOCIAL_CLIPR_FFMPEG=$HOME/Downloads/ffmpeg
python3 -m social_clipr run --input /path/to/screen-recording.mp4 --profile shorts-vertical-fit
```

Output: **`outputs/<stem>/rendered-shorts-vertical-fit.mp4`** at **1080×1920**.

**1920×1080 horizontal** (e.g. YouTube landscape):

```bash
export SOCIAL_CLIPR_FFMPEG=$HOME/Downloads/ffmpeg
python3 -m social_clipr run --input /path/to/video.mp4 --profile youtube-horizontal
```

Bundled profiles live under **`configs/encode/`**; use **`--profile <id>`** for any profile id that matches a file there.

#### Word-level captions (one word per on-screen cue)

There is **no separate CLI flag** for this: a normal **`run`** always generates **`captions.srt`** and **`captions.vtt`** with **one subtitle entry per word**, then passes that **`.srt`** to FFmpeg for burn-in (when render is **not** stub).

1. **Transcribe** — `transcript.json` includes **`word_cues`** and **`word_cue_count`**. If **`configs/stt.json`** uses **Whisper** (`whisper_cli` or `faster_whisper`) and the engine returns per-word timestamps, those become the cue times. Otherwise ( **`stub`** or segment-only STT output) words are split from each segment’s text with deterministic timing rules and the same **`word_cues`** list is still written.
2. **Captions** — the SRT/VTT writer reads that normalized list, so each line shown in players (and each burn-in draw) is a **single word** for its time range.
3. **Render** — burning requires **real FFmpeg**, i.e. **do not set** **`SOCIAL_CLIPR_RENDER=stub`**. Stub render copies the input file and **does not** burn subtitles; use **`--subtitle-style`** / **`--subtitle-font-size`** as usual for font, color, and placement (**`configs/subtitle_styles/`**).

Example — real vertical encode with burned **one-word** subtitles (after **`ffmpeg`** and `configs/stt.json` are set up as you want):

```bash
unset SOCIAL_CLIPR_RENDER
python3 -m social_clipr run \
  --input ./your-video.mp4 \
  --profile shorts-vertical \
  --subtitle-style minimal
```

To confirm cue granularity before sharing the MP4, open **`outputs/<stem>/captions.srt`** or check **`word_cues`** in **`outputs/<stem>/transcript.json`**.

#### Edit `transcript.json` and re-run without STT

Run from the **repository root** (so **`configs/`** loads; or pass **`--config-dir`** to your config tree).

**1. Full run** — same **`--input`** path, profile, and subtitle style you want in the final MP4:

```bash
python3 -m social_clipr run \
  --input ~/Downloads/x_20260311.mp4 \
  --profile youtube-horizontal \
  --subtitle-style purple_lower_third
```

For that filename, artifacts land under **`outputs/x_20260311/`** (folder name = basename without **`.mp4`**). The rendered file is **`rendered-youtube-horizontal.mp4`**. For real burn-in, **do not** set **`SOCIAL_CLIPR_RENDER=stub`**.

**2. Edit the transcript** — open **`outputs/x_20260311/transcript.json`** and change **`segments`** (phrases + coarse timing) and/or **`word_cues`** (one word per on-screen cue). If **`word_cues`** is non-empty, captions prefer it over **`segments`** text; see the next step.

**3. Re-run without Whisper** — use the **same** **`--input`** path (stem must match the job folder) and the **same** **`--profile`** / **`--subtitle-style`** (and **`--config-dir`** if you used it):

```bash
python3 -m social_clipr run \
  --input ~/Downloads/x_20260311.mp4 \
  --profile youtube-horizontal \
  --subtitle-style purple_lower_third \
  --skip-transcribe
```

**4. If you only edited `segments`** — add **`--refresh-word-cues-from-segments`** (rewrites **`word_cues`** in the JSON) or **`--captions-from-segments`** (this run only; JSON unchanged).

**5. Confirm** — check **`outputs/<stem>/captions.srt`** for text/timing, then open **`outputs/<stem>/rendered-<profile>.mp4`** for burned-in subtitles. Logs include **`[pipeline] captions:`** (which source drove cues) and a **stub render** warning if the MP4 has no burn-in.

**`run_summary.json`** records **`transcript_source`** / **`transcribe_skipped`** when transcribe was skipped.

Details: **[docs/operator-guide.md](docs/operator-guide.md)** → *Transcript polish without re-running STT*.

| Option | Description |
|--------|-------------|
| `--input` | Path to an existing, non-empty **`.mp4`** file (readable). |
| `--profile` | **Encode profile id** — must match a JSON file under `configs/encode/`. **Omit** when **`--preset`** supplies `profile`. |
| `--preset` | Optional **job preset** JSON (see **`social-clipr preset save`**): `profile`, `subtitle_style`, optional `config_dir`. Explicit **`--profile`**, **`--subtitle-style`**, **`--subtitle-font-size`**, and **`--config-dir`** override preset fields. |
| `--config-dir` | Optional. Directory that contains **`encode/`** and **`subtitle_styles/`** (and **`stt.json`**). If omitted, the loader uses `./configs` when present, otherwise the repo’s bundled **`configs/`**; a preset may supply **`config_dir`** when the CLI omits this flag. |
| `--subtitle-style` | **Burn-in preset** id. Default **`minimal`**, or the preset’s value when **`--preset`** is set. **`bold_social`** is the bundled alternate. Ignored when **`SOCIAL_CLIPR_RENDER=stub`**. |
| `--subtitle-font-size` | Optional **pixel** size for burned-in subtitles (overrides the style preset’s `font_size`). Allowed range **8–512**. Ignored when **`SOCIAL_CLIPR_RENDER=stub`**. |
| `--skip-transcribe` | Use existing **`outputs/<stem>/transcript.json`**; skip STT; still run ingest validation, captions, render, package. |
| `--refresh-word-cues-from-segments` | Before captions, rebuild **`word_cues`** from **`segments`** and rewrite **`transcript.json`**. |
| `--captions-from-segments` | This run only: ignore stored **`word_cues`**; build captions from **`segments`** (does not rewrite **`transcript.json`**). |

Logs include a **`[pipeline] captions:`** line (stored **`word_cues`** vs **segments**) and, when **`SOCIAL_CLIPR_RENDER=stub`**, a note that the rendered **`.mp4`** has **no** burn-in.

Save a reusable preset:

```bash
python3 -m social_clipr preset save \
  --profile shorts-vertical \
  --subtitle-style bold_social \
  --config-dir ./configs \
  -o ./my-job.json
python3 -m social_clipr run --input ./video.mp4 --preset ./my-job.json
```

`run_summary.json` and `metadata_draft.json` include **`job_preset`** (absolute path) when `--preset` was used.

Progress is logged per stage (`[pipeline] 1/5 ingest:` … `5/5 package:`). On success, artifact paths are printed at the end.

Invalid or incomplete config (bad JSON, missing folders or **`stt.json`**, fewer than two subtitle styles, `id` not matching the filename stem) fails fast with a **`Config error:`** message and exit code **`2`**.

**Environment (optional)**

| Variable | Effect |
|----------|--------|
| `SOCIAL_CLIPR_RENDER=stub` | Skip FFmpeg; copy input to `rendered-*.mp4` (tests / smoke script). |
| `SOCIAL_CLIPR_TRANSCRIBE=stub` | Skip Whisper; use deterministic stub transcript. |
| `SOCIAL_CLIPR_WHISPER_MODEL` | Overrides **`model`** in `configs/stt.json` when non-empty. |
| `SOCIAL_CLIPR_WHISPER_LANGUAGE` | If set, overrides **`language`** in `configs/stt.json` for Whisper. |
| `SOCIAL_CLIPR_SUBTITLE_FONT_SIZE` | If set to an integer **8–512**, used as burned-in subtitle size when **`run`** does not pass **`--subtitle-font-size`** and the job preset (if any) omits **`subtitle_font_size`**. |
| `SOCIAL_CLIPR_FFMPEG` | If set (non-empty), use this **ffmpeg** executable: **absolute path** to a file, or a **command name** resolved via `PATH` (same as `shutil.which`). When unset, the pipeline uses **`ffmpeg`** on `PATH`. Ignored when **`SOCIAL_CLIPR_RENDER=stub`**. |

**Subtitle font size precedence for `run`:** **`--subtitle-font-size`** → job preset **`subtitle_font_size`** → **`SOCIAL_CLIPR_SUBTITLE_FONT_SIZE`** → subtitle style JSON **`font_size`**. **`social-clipr preset save`** accepts **`--subtitle-font-size`** to store **`subtitle_font_size`** in the preset.

### Configuration

Declarative files live under **`configs/`** in the repository (or under **`--config-dir`**). They are **JSON**, validated at startup:

| Path | Purpose |
|------|---------|
| `configs/encode/<id>.json` | One **encode profile** per file. The `id` field must equal the filename stem (e.g. `shorts-vertical`). **`video_filter`** must prove the output frame size with **`crop=<width>:<height>`**, **`pad=<width>:<height>`**, or (if there is no crop/pad in the chain) **`scale=<width>:<height>`**. FFmpeg also uses **`width`/`height`/`frame_rate`**, video codec, **`crf`**, **`encoder_preset`**, audio codec, and **`audio_bitrate_kbps`**. Output video uses **`yuv420p`** for broad player compatibility. |
| `configs/subtitle_styles/<id>.json` | **Subtitle / burn-in style** presets (font, ASS-like **`primary_color`** / **`outline_color`**, **`outline_width`**, **`margin_v`**, ASS **`alignment`**). At least **two** styles are required. Bundled examples include **`minimal`**, **`bold_social`**, and **`purple_lower_third`** (lower-center purple text for one-word cues). The render stage passes them to FFmpeg **`subtitles=`** as **`force_style`** (libass). **`font_family`** must match a font **installed on the machine that runs FFmpeg**; on **macOS**, use **Font Book** to get the exact name (see [macOS: Font Book and `font_family`](#macos-font-book-and-font_family)). |
| `configs/stt.json` | **Speech-to-text:** `engine` is `stub` (deterministic transcript), `whisper_cli` (OpenAI **`whisper`** on `PATH`), or `faster_whisper` (optional **`pip install faster-whisper`**, local CPU). For Whisper engines, **`model`** is required (e.g. `tiny`, `base`). **`language`** is optional (ISO code; empty = auto). |

Copy and edit these files for your own presets, or point `--config-dir` at a separate tree (same layout: `encode/*.json`, `subtitle_styles/*.json`, and **`stt.json`**).

#### Custom subtitle styles — font family and primary color (examples)

The loader requires **at least two** files under **`subtitle_styles/`**, and each file’s **`id`** must equal its filename stem (e.g. `serif_brand.json` → `"id": "serif_brand"`). Colors use **ASS `&HAABBGGRR&`** form (see `social_clipr.render._normalize_ass_colour`); **fonts must exist on the system** that runs FFmpeg/libass.

##### macOS: Font Book and font_family

1. Open **Font Book** (in **Applications**, or Spotlight: “Font Book”).
2. Find a font you want (e.g. **Courier**, **Helvetica Neue**, **Phosphate**, or a face you installed). Confirm it is **enabled** and not flagged with errors.
3. Put the **exact name** Font Book shows for that family into JSON **`font_family`** (same spelling and spacing).
4. If you change **`font_family`** but the burned-in text still looks like the old face, libass is probably **substituting** a fallback: in Font Book, select the font, then **File → Show Font Info** (or the **Info** inspector, **⌘I**) and try the **PostScript name** as **`font_family`** instead of the display name.
5. Re-run **`run`** with a **real** render (not **`SOCIAL_CLIPR_RENDER=stub`**) and open the **new** **`rendered-*.mp4`**.

Bundled presets use **Arial** because it is widely available; many other system fonts work the same way once the string matches Font Book / PostScript naming.

**1) Serif brand font** — add a style that only changes **`font_family`** (and keeps lower-center **`margin_v`** / **`alignment`** like the bundled presets):

```bash
mkdir -p operator-styles/{encode,subtitle_styles}
cp configs/stt.json operator-styles/
cp configs/encode/shorts-vertical.json operator-styles/encode/
cp configs/subtitle_styles/minimal.json operator-styles/subtitle_styles/
```

Create **`operator-styles/subtitle_styles/serif_brand.json`**:

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

Run with **`--subtitle-style`** pointing at that **`id`**:

```bash
python3 -m social_clipr run \
  --input ./your-video.mp4 \
  --profile shorts-vertical \
  --subtitle-style serif_brand \
  --config-dir ./operator-styles
```

**2) High-visibility primary color** — same **`operator-styles/`** tree; add **`operator-styles/subtitle_styles/high_visibility.json`** (green text via **`primary_color`**; **`&H0000FF00&`** is opaque green in **BBGGRR** byte order):

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

You must keep **at least two** styles in **`operator-styles/subtitle_styles/`** (e.g. leave **`minimal.json`** in place). Then:

```bash
python3 -m social_clipr run \
  --input ./your-video.mp4 \
  --profile shorts-vertical \
  --subtitle-style high_visibility \
  --config-dir ./operator-styles
```

**3) Purple text, lower-center (bundled example)** — the repo ships **`configs/subtitle_styles/purple_lower_third.json`** so you can render **one-word-per-cue** captions (default pipeline behavior) in **purple** with the same **`margin_v`** / **`alignment`** as the other social presets (**`2`** = bottom-center):

```json
{
  "id": "purple_lower_third",
  "font_family": "Arial",
  "font_size": 38,
  "primary_color": "&HD355BA&",
  "outline_color": "&H000000&",
  "outline_width": 2,
  "margin_v": 160,
  "alignment": 2
}
```

Run with the default **`configs/`** tree:

```bash
python3 -m social_clipr run \
  --input ./your-video.mp4 \
  --profile shorts-vertical \
  --subtitle-style purple_lower_third
```

**Reference run — `youtube-horizontal` + `purple_lower_third` (exact command and CLI output):**

```text
(.venv) $ python3 -m social_clipr run   --input ~/Downloads/x_20260311.mp4   --profile youtube-horizontal   --subtitle-style purple_lower_third
[pipeline] 1/5 ingest: validating input
[pipeline] 1/5 ingest: ok (x_20260311.mp4)
[pipeline] 2/5 transcribe: generating transcript
[pipeline] transcribe: using whisper_cli (model=tiny, segments=29)
[pipeline] 2/5 transcribe: ok (outputs/x_20260311/transcript.json)
[pipeline] 3/5 captions: writing SRT/VTT
[pipeline] 3/5 captions: ok (outputs/x_20260311/captions.srt, outputs/x_20260311/captions.vtt)
[pipeline] 4/5 render: profile=youtube-horizontal, subtitle_style=purple_lower_third (config from social-clipr/configs)
[pipeline] 4/5 render: ok (outputs/x_20260311/rendered-youtube-horizontal.mp4)
[pipeline] 5/5 package: run summary and metadata
[pipeline] 5/5 package: ok (outputs/x_20260311/run_summary.json, outputs/x_20260311/metadata_draft.json)
[pipeline] complete: all stages finished
Transcript JSON: outputs/x_20260311/transcript.json
Transcript TXT: outputs/x_20260311/transcript.txt
Captions SRT: outputs/x_20260311/captions.srt
Captions VTT: outputs/x_20260311/captions.vtt
Rendered MP4: outputs/x_20260311/rendered-youtube-horizontal.mp4
Run summary: outputs/x_20260311/run_summary.json
Metadata draft: outputs/x_20260311/metadata_draft.json
(.venv) $
```

(`primary_color` uses ASS **`&HAABBGGRR&`** / six-digit **`&HBBGGRR&`**; burn-in normalizes it for libass.)

On **Linux**, if **Georgia** is missing, substitute an installed **`font_family`** (e.g. **DejaVu Serif**) in **`serif_brand.json`**. More operator context: **[docs/operator-guide.md](docs/operator-guide.md)**.

### Output layout

All artifacts for one run go under:

```text
outputs/<input-basename-without-extension>/
  transcript.json
  transcript.txt
  captions.srt
  captions.vtt
  rendered-<encode-profile-id>.mp4
  run_summary.json
  metadata_draft.json
```

`<input-basename>` is the filename of `--input` without `.mp4`. The video filename uses the encode profile **`id`** (same as `--profile`). The `outputs/` tree is gitignored except `outputs/.gitkeep`.

**`run_summary.json`** includes a **`bundle`** object: **`expected_files`** (ordered manifest), **`layout_version`**, **`render_mode`** (`stub_copy` vs `ffmpeg`), and **`video_includes_burned_subtitles`** (false when **`SOCIAL_CLIPR_RENDER=stub`**). It also records **`subtitle_font_size`**, the resolved burn-in size (CLI / preset / env override or the subtitle style preset default). **`metadata_draft.json`** echoes **`encode_profile`**, **`subtitle_style`**, **`subtitle_font_size`**, **`source_media`**, and export hints under **`export`** for packaging tools.

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `2` | User error (e.g. missing/invalid input, config load failure, unknown encode profile or subtitle style, ingest validation failure) |

## License

This project is licensed under the [MIT License](LICENSE.md).

## Development

```bash
python3 -m pytest
```

Coverage (HTML report in `htmlcov/`, XML for Codecov):

```bash
python3 -m pytest --cov=social_clipr --cov-report=term-missing --cov-report=html
```

CI uploads **`coverage.xml`** to [Codecov](https://codecov.io/gh/djgoosen/Social-CLIpper) after tests. Add the repo in the Codecov app if the badge is missing; if uploads fail, set a **`CODECOV_TOKEN`** repository secret from Codecov → **Settings**. For a **private** GitHub repo, the README Codecov badge usually needs the **`?token=…`** image URL from Codecov → **Settings** → **Badge** (see HTML comment above the badge).

## Smoke test (end-to-end)

From the repo root, `scripts/smoke_run.sh` runs the full CLI pipeline and checks the job bundle. See the **comment block at the top of the script** for the full contract.

| Mode | Env | What it does |
|------|-----|----------------|
| **Quick (default)** | _(none)_ | Stub transcribe + stub render; tiny fake `.mp4`. **No FFmpeg or Whisper.** Safe for CI. |
| **Real encode + burn-in** | `SOCIAL_CLIPR_SMOKE_REAL=1` | Builds a short **lavfi** H.264+AAC clip, runs **real** FFmpeg (transcode + **burned subtitles**). Requires **`ffmpeg`** on `PATH`. Asserts `run_summary.json` has `bundle.render_mode == "ffmpeg"` and burned-subtitle flag **true**. |
| **Strict Whisper** | `SOCIAL_CLIPR_SMOKE_WHISPER=1` **with** `SOCIAL_CLIPR_SMOKE_REAL=1` | Fails fast if the **`whisper`** CLI is missing — for **local** checks only; omit in CI unless you install Whisper. |

Examples:

```bash
bash scripts/smoke_run.sh
```

```bash
PYTHON=.venv/bin/python bash scripts/smoke_run.sh
```

```bash
SOCIAL_CLIPR_SMOKE_REAL=1 PYTHON=.venv/bin/python bash scripts/smoke_run.sh
```

Pytest includes **`tests/test_smoke.py`**: quick smoke via subprocess, optional real-mode test when `ffmpeg` exists, and **`faster_whisper`** import failure falling back to stub (no model downloads).

Git log: `git log --pretty=format:"%h | %ad | %s" --date=short --numstat --reverse > git_history_compact.txt`
