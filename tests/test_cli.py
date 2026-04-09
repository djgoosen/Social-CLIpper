import json
from pathlib import Path

import pytest
from social_clipr.cli import main
from social_clipr.pipeline import validate_subtitle_font_size

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_cli_help_returns_zero() -> None:
    result = main([])
    assert result == 0


def test_cli_version_returns_zero(capsys) -> None:  # type: ignore[no-untyped-def]
    result = main(["--version"])
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.strip()


def test_run_requires_profile_or_preset(tmp_path, capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    inp = tmp_path / "a.mp4"
    inp.write_bytes(b"x")
    result = main(["run", "--input", str(inp)])
    captured = capsys.readouterr()
    assert result == 2
    assert "Either --profile or --preset" in captured.out


def test_preset_save_and_run_records_job_preset(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    preset = tmp_path / "my-preset.json"
    assert (
        main(
            [
                "preset",
                "save",
                "-o",
                str(preset),
                "--profile",
                "shorts-vertical",
                "--subtitle-style",
                "bold_social",
                "--config-dir",
                str(configs),
            ]
        )
        == 0
    )
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    assert main(["run", "--input", str(inp), "--preset", str(preset)]) == 0
    job = tmp_path / "outputs" / "clip"
    summary = json.loads((job / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["profile"] == "shorts-vertical"
    assert summary["subtitle_style"] == "bold_social"
    assert summary["subtitle_font_size"] == 44
    assert summary["job_preset"] == str(preset.resolve())
    meta = json.loads((job / "metadata_draft.json").read_text(encoding="utf-8"))
    assert meta["subtitle_style"] == "bold_social"
    assert meta["subtitle_font_size"] == 44
    assert meta["job_preset"] == str(preset.resolve())


def test_run_explicit_subtitle_overrides_preset(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    preset = tmp_path / "p.json"
    assert (
        main(
            [
                "preset",
                "save",
                "-o",
                str(preset),
                "--profile",
                "shorts-vertical",
                "--subtitle-style",
                "bold_social",
                "--config-dir",
                str(configs),
            ]
        )
        == 0
    )
    inp = tmp_path / "v.mp4"
    inp.write_bytes(b"x")
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--preset",
                str(preset),
                "--subtitle-style",
                "minimal",
            ]
        )
        == 0
    )
    summary = json.loads(
        (tmp_path / "outputs" / "v" / "run_summary.json").read_text(encoding="utf-8")
    )
    assert summary["subtitle_style"] == "minimal"
    assert summary["subtitle_font_size"] == 36


def test_run_missing_input_returns_nonzero(capsys) -> None:  # type: ignore[no-untyped-def]
    result = main(
        ["run", "--input", "does-not-exist.mp4", "--profile", "shorts-vertical"]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert "Ingest validation error" in captured.out


def test_run_unsupported_profile_returns_nonzero(capsys) -> None:  # type: ignore[no-untyped-def]
    result = main(["run", "--input", "sample.mp4", "--profile", "unknown-profile"])
    captured = capsys.readouterr()
    assert result == 2
    assert "Unsupported profile" in captured.out


def test_run_youtube_horizontal_profile_end_to_end_stub(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """Bundled youtube-horizontal profile is selectable on CLI (stub render/transcribe)."""
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    inp = tmp_path / "wide.mp4"
    inp.write_bytes(b"fake-mp4")
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "youtube-horizontal",
                "--config-dir",
                str(configs),
            ]
        )
        == 0
    )
    job = tmp_path / "outputs" / "wide"
    summary = json.loads((job / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["profile"] == "youtube-horizontal"
    assert summary["subtitle_font_size"] == 36
    assert (job / "rendered-youtube-horizontal.mp4").exists()
    assert summary["artifacts"]["video_mp4"] == "rendered-youtube-horizontal.mp4"


def test_validate_subtitle_font_size_bounds() -> None:
    validate_subtitle_font_size(8)
    validate_subtitle_font_size(512)
    with pytest.raises(ValueError, match="at least"):
        validate_subtitle_font_size(7)
    with pytest.raises(ValueError, match="at most"):
        validate_subtitle_font_size(513)


def test_run_subtitle_font_size_out_of_range_returns_nonzero(
    tmp_path, capsys, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    inp = tmp_path / "a.mp4"
    inp.write_bytes(b"x")
    result = main(
        [
            "run",
            "--input",
            str(inp),
            "--profile",
            "shorts-vertical",
            "--subtitle-font-size",
            "4",
            "--config-dir",
            str(configs),
        ]
    )
    out = capsys.readouterr().out
    assert result == 2
    assert "Config error" in out
    assert "at least 8" in out


def test_run_subtitle_font_size_override_pipeline_log(
    tmp_path, capsys, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "shorts-vertical",
                "--subtitle-font-size",
                "36",
                "--config-dir",
                str(configs),
            ]
        )
        == 0
    )
    captured = capsys.readouterr().out
    assert "subtitle_font_size=36" in captured
    job = tmp_path / "outputs" / "clip"
    summary = json.loads((job / "run_summary.json").read_text(encoding="utf-8"))
    meta = json.loads((job / "metadata_draft.json").read_text(encoding="utf-8"))
    assert summary["subtitle_font_size"] == 36
    assert meta["subtitle_font_size"] == 36


def test_run_unknown_subtitle_style_returns_nonzero(capsys) -> None:  # type: ignore[no-untyped-def]
    result = main(
        [
            "run",
            "--input",
            "sample.mp4",
            "--profile",
            "shorts-vertical",
            "--subtitle-style",
            "no-such-style",
        ]
    )
    captured = capsys.readouterr()
    assert result == 2
    assert "Unknown subtitle style" in captured.out


def test_run_render_fails_when_ffmpeg_missing_and_not_stub(
    tmp_path, capsys, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.delenv("SOCIAL_CLIPR_RENDER", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("social_clipr.render._ffmpeg_path", lambda: None)
    input_file = tmp_path / "sample.mp4"
    input_file.write_bytes(b"x")
    result = main(["run", "--input", str(input_file), "--profile", "shorts-vertical"])
    captured = capsys.readouterr()
    assert result == 2
    assert "Render error" in captured.out
    assert "ffmpeg" in captured.out.lower()


def test_run_writes_deterministic_transcript_artifacts(
    tmp_path, capsys, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    input_file = tmp_path / "sample.mp4"
    input_file.write_bytes(b"fake-mp4-content")

    result = main(["run", "--input", str(input_file), "--profile", "shorts-vertical"])
    captured = capsys.readouterr()

    assert result == 0
    assert "[pipeline] 1/5 ingest:" in captured.out
    assert "[pipeline] 2/5 transcribe:" in captured.out
    assert "[pipeline] 3/5 captions:" in captured.out
    assert "[pipeline] 4/5 render:" in captured.out
    assert "[pipeline] 5/5 package:" in captured.out
    assert "[pipeline] complete:" in captured.out
    assert "Transcript JSON:" in captured.out
    assert "Transcript TXT:" in captured.out
    assert "Rendered MP4:" in captured.out
    assert "Run summary:" in captured.out
    assert "Metadata draft:" in captured.out

    out_dir = tmp_path / "outputs" / "sample"
    transcript_json = out_dir / "transcript.json"
    transcript_txt = out_dir / "transcript.txt"
    captions_srt = out_dir / "captions.srt"
    captions_vtt = out_dir / "captions.vtt"
    rendered_mp4 = out_dir / "rendered-shorts-vertical.mp4"
    run_summary = out_dir / "run_summary.json"
    metadata_draft = out_dir / "metadata_draft.json"
    assert transcript_json.exists()
    assert transcript_txt.exists()
    assert captions_srt.exists()
    assert captions_vtt.exists()
    assert rendered_mp4.exists()
    assert run_summary.exists()
    assert metadata_draft.exists()

    summary_data = json.loads(run_summary.read_text(encoding="utf-8"))
    assert summary_data["status"] == "success"
    assert summary_data["profile"] == "shorts-vertical"
    assert summary_data["subtitle_style"] == "minimal"
    assert summary_data["subtitle_font_size"] == 36
    meta_data = json.loads(metadata_draft.read_text(encoding="utf-8"))
    assert meta_data["subtitle_font_size"] == 36
    assert summary_data["bundle"]["render_mode"] == "stub_copy"
    assert summary_data["bundle"]["video_includes_burned_subtitles"] is False
    arts = summary_data["artifacts"]
    assert arts["transcript_json"] == "transcript.json"
    assert arts["transcript_txt"] == "transcript.txt"
    assert arts["captions_srt"] == "captions.srt"
    assert arts["captions_vtt"] == "captions.vtt"
    assert arts["video_mp4"] == "rendered-shorts-vertical.mp4"

    first_json = transcript_json.read_text(encoding="utf-8")
    first_txt = transcript_txt.read_text(encoding="utf-8")
    first_srt = captions_srt.read_text(encoding="utf-8")
    first_vtt = captions_vtt.read_text(encoding="utf-8")
    first_mp4 = rendered_mp4.read_bytes()
    first_summary = run_summary.read_text(encoding="utf-8")
    first_meta = metadata_draft.read_text(encoding="utf-8")
    assert " --> " in first_srt
    assert "WEBVTT" in first_vtt

    second_result = main(
        ["run", "--input", str(input_file), "--profile", "shorts-vertical"]
    )
    assert second_result == 0

    second_json = transcript_json.read_text(encoding="utf-8")
    second_txt = transcript_txt.read_text(encoding="utf-8")
    second_srt = captions_srt.read_text(encoding="utf-8")
    second_vtt = captions_vtt.read_text(encoding="utf-8")
    second_mp4 = rendered_mp4.read_bytes()
    second_summary = run_summary.read_text(encoding="utf-8")
    second_meta = metadata_draft.read_text(encoding="utf-8")
    assert first_json == second_json
    assert first_txt == second_txt
    assert first_srt == second_srt
    assert first_vtt == second_vtt
    assert first_mp4 == second_mp4
    assert first_summary == second_summary
    assert first_meta == second_meta


def test_run_subtitle_font_size_from_env_when_no_cli_or_preset(
    tmp_path, capsys, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_SUBTITLE_FONT_SIZE", "88")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    inp = tmp_path / "envonly.mp4"
    inp.write_bytes(b"x")
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "shorts-vertical",
                "--config-dir",
                str(configs),
            ]
        )
        == 0
    )
    assert "subtitle_font_size=88" in capsys.readouterr().out
    job = tmp_path / "outputs" / "envonly"
    summary = json.loads((job / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["subtitle_font_size"] == 88


def test_run_subtitle_font_size_preset_beats_env(
    tmp_path, capsys, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_SUBTITLE_FONT_SIZE", "99")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    preset = tmp_path / "preset.json"
    assert (
        main(
            [
                "preset",
                "save",
                "-o",
                str(preset),
                "--profile",
                "shorts-vertical",
                "--subtitle-style",
                "minimal",
                "--subtitle-font-size",
                "55",
                "--config-dir",
                str(configs),
            ]
        )
        == 0
    )
    inp = tmp_path / "p.mp4"
    inp.write_bytes(b"x")
    assert main(["run", "--input", str(inp), "--preset", str(preset)]) == 0
    assert "subtitle_font_size=55" in capsys.readouterr().out
    assert "subtitle_font_size=99" not in capsys.readouterr().out
    summary = json.loads(
        (tmp_path / "outputs" / "p" / "run_summary.json").read_text(encoding="utf-8")
    )
    assert summary["subtitle_font_size"] == 55


def test_run_subtitle_font_size_cli_beats_preset_and_env(
    tmp_path, capsys, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_SUBTITLE_FONT_SIZE", "99")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    preset = tmp_path / "preset.json"
    assert (
        main(
            [
                "preset",
                "save",
                "-o",
                str(preset),
                "--profile",
                "shorts-vertical",
                "--subtitle-style",
                "minimal",
                "--subtitle-font-size",
                "55",
                "--config-dir",
                str(configs),
            ]
        )
        == 0
    )
    inp = tmp_path / "p.mp4"
    inp.write_bytes(b"x")
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--preset",
                str(preset),
                "--subtitle-font-size",
                "24",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "subtitle_font_size=24" in out
    assert "subtitle_font_size=55" not in out
    summary = json.loads(
        (tmp_path / "outputs" / "p" / "run_summary.json").read_text(encoding="utf-8")
    )
    assert summary["subtitle_font_size"] == 24


def test_run_subtitle_font_size_invalid_env_returns_nonzero(
    tmp_path, capsys, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_SUBTITLE_FONT_SIZE", "not-a-number")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    inp = tmp_path / "a.mp4"
    inp.write_bytes(b"x")
    result = main(
        [
            "run",
            "--input",
            str(inp),
            "--profile",
            "shorts-vertical",
            "--config-dir",
            str(configs),
        ]
    )
    out = capsys.readouterr().out
    assert result == 2
    assert "Config error" in out
    assert "integer" in out


def test_run_help_mentions_skip_transcribe(capsys) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SystemExit) as exc:
        main(["run", "--help"])
    assert exc.value.code == 0
    combined = capsys.readouterr().out + capsys.readouterr().err
    assert "--skip-transcribe" in combined
    assert "--refresh-word-cues-from-segments" in combined
    assert "--captions-from-segments" in combined


def test_run_skip_transcribe_missing_transcript(
    tmp_path, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "shorts-vertical",
                "--config-dir",
                str(configs),
                "--skip-transcribe",
            ]
        )
        == 2
    )
    assert "Transcript resume" in capsys.readouterr().out


def test_run_skip_transcribe_skips_transcribe_stage(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    job = tmp_path / "outputs" / "clip"
    job.mkdir(parents=True)
    (job / "transcript.json").write_text(
        json.dumps(
            {
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "hello"},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (job / "transcript.txt").write_text("hello\n", encoding="utf-8")

    called: list[bool] = []

    def boom(*_a, **_k):
        called.append(True)
        raise AssertionError(
            "write_transcript_artifacts should not run with --skip-transcribe"
        )

    monkeypatch.setattr("social_clipr.pipeline.write_transcript_artifacts", boom)
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "shorts-vertical",
                "--config-dir",
                str(configs),
                "--skip-transcribe",
            ]
        )
        == 0
    )
    assert called == []
    summary = json.loads((job / "run_summary.json").read_text(encoding="utf-8"))
    assert summary.get("transcript_source") == "resumed_from_disk"
    assert summary.get("transcribe_skipped") is True
    meta = json.loads((job / "metadata_draft.json").read_text(encoding="utf-8"))
    assert meta.get("transcript_source") == "resumed_from_disk"


def test_run_refresh_word_cues_updates_transcript(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "shorts-vertical",
                "--config-dir",
                str(configs),
            ]
        )
        == 0
    )
    job = tmp_path / "outputs" / "clip"
    data = json.loads((job / "transcript.json").read_text(encoding="utf-8"))
    data["segments"] = [{"start": 0.0, "end": 2.0, "text": "alpha bravo"}]
    data["word_cues"] = [{"start": 0.0, "end": 1.0, "text": "wrong"}]
    (job / "transcript.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "shorts-vertical",
                "--config-dir",
                str(configs),
                "--skip-transcribe",
                "--refresh-word-cues-from-segments",
            ]
        )
        == 0
    )
    updated = json.loads((job / "transcript.json").read_text(encoding="utf-8"))
    texts = [c["text"] for c in updated["word_cues"]]
    assert "alpha" in texts and "bravo" in texts


def test_run_captions_from_segments_ignores_word_cues_without_rewriting_json(
    tmp_path, monkeypatch, capsys
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("SOCIAL_CLIPR_RENDER", "stub")
    monkeypatch.setenv("SOCIAL_CLIPR_TRANSCRIBE", "stub")
    monkeypatch.chdir(tmp_path)
    configs = REPO_ROOT / "configs"
    inp = tmp_path / "clip.mp4"
    inp.write_bytes(b"x")
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "shorts-vertical",
                "--config-dir",
                str(configs),
            ]
        )
        == 0
    )
    job = tmp_path / "outputs" / "clip"
    data = json.loads((job / "transcript.json").read_text(encoding="utf-8"))
    data["segments"] = [{"start": 0.0, "end": 2.0, "text": "alpha bravo"}]
    data["word_cues"] = [{"start": 0.0, "end": 1.0, "text": "wrong"}]
    (job / "transcript.json").write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )
    assert (
        main(
            [
                "run",
                "--input",
                str(inp),
                "--profile",
                "shorts-vertical",
                "--config-dir",
                str(configs),
                "--skip-transcribe",
                "--captions-from-segments",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "ignoring" in out and "word_cue" in out
    disk = json.loads((job / "transcript.json").read_text(encoding="utf-8"))
    assert disk["word_cues"][0]["text"] == "wrong"
    srt = (job / "captions.srt").read_text(encoding="utf-8")
    assert "alpha" in srt and "bravo" in srt
    assert "wrong" not in srt
