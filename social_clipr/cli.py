"""CLI entrypoint for Social Clipr."""

from __future__ import annotations

import argparse
from pathlib import Path

from social_clipr.config_loader import ConfigError, load_pipeline_config
from social_clipr.job_preset import JobPresetError, load_job_preset, save_job_preset
from social_clipr.pipeline import (
    run_social_clipr_job,
    subtitle_font_size_from_environment,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="social-clipr",
        description="CLI-first video pipeline for Social Clipr.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit.",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser(
        "run",
        help="Run a pipeline job.",
        description="Run the Social Clipr pipeline for one input video. "
        "Use --preset to load profile and subtitle defaults; explicit flags override the preset.",
    )
    run_parser.add_argument(
        "--input",
        required=True,
        help="Path to local input .mp4 file.",
    )
    run_parser.add_argument(
        "--profile",
        default=None,
        metavar="ID",
        help="Encode profile id (configs/encode/<id>.json). "
        "Required unless --preset supplies profile.",
    )
    run_parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Directory containing encode/ and subtitle_styles/ (default: ./configs or repo configs/).",
    )
    run_parser.add_argument(
        "--subtitle-style",
        default=None,
        metavar="ID",
        help="Subtitle burn-in preset id (configs/subtitle_styles/<id>.json). "
        "Default: minimal, or the value from --preset when set.",
    )
    run_parser.add_argument(
        "--subtitle-font-size",
        type=int,
        default=None,
        metavar="PX",
        help="Override burned-in subtitle font size in pixels (default: from subtitle style preset).",
    )
    run_parser.add_argument(
        "--preset",
        type=Path,
        default=None,
        help="Job preset JSON (profile, subtitle_style, optional config_dir, optional subtitle_font_size).",
    )
    run_parser.add_argument(
        "--skip-transcribe",
        action="store_true",
        help="Skip speech-to-text: require outputs/<stem>/transcript.json and continue with captions, render, package. "
        "Ingest still validates --input .mp4 (stem must match the job folder name).",
    )
    run_parser.add_argument(
        "--refresh-word-cues-from-segments",
        action="store_true",
        help="Before captions, rebuild word_cues from segments only and rewrite transcript.json (optional polish).",
    )
    run_parser.add_argument(
        "--captions-from-segments",
        action="store_true",
        help="For this run only, ignore stored word_cues in transcript.json and build captions from segments "
        "(does not rewrite transcript.json; use --refresh-word-cues-from-segments to persist).",
    )

    preset_parser = subparsers.add_parser(
        "preset",
        help="Job preset helpers.",
        description="Create reusable job preset files (encode profile, subtitle style, optional config dir).",
    )
    preset_sub = preset_parser.add_subparsers(dest="preset_cmd", required=True)
    save_p = preset_sub.add_parser(
        "save",
        help="Write a job preset JSON file.",
    )
    save_p.add_argument(
        "--profile",
        required=True,
        metavar="ID",
        help="Encode profile id to store in the preset.",
    )
    save_p.add_argument(
        "--subtitle-style",
        default="minimal",
        metavar="ID",
        help="Subtitle style id (default: minimal).",
    )
    save_p.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="Optional configs root to record in the preset (must exist).",
    )
    save_p.add_argument(
        "--subtitle-font-size",
        type=int,
        default=None,
        metavar="PX",
        help="Optional subtitle font size to store in the preset (8–512).",
    )
    save_p.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Preset JSON path to write.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        from social_clipr import __version__

        print(__version__)
        return 0
    if args.command == "preset":
        try:
            save_job_preset(
                args.output,
                profile=args.profile,
                subtitle_style=args.subtitle_style,
                config_dir=args.config_dir,
                subtitle_font_size=args.subtitle_font_size,
            )
        except JobPresetError as exc:
            print(f"Preset error: {exc}")
            return 2
        print(f"Wrote preset {args.output}")
        return 0
    if args.command == "run":
        preset_data: dict | None = None
        preset_path = args.preset
        if preset_path is not None:
            try:
                preset_data = load_job_preset(preset_path)
            except JobPresetError as exc:
                print(f"Preset error: {exc}")
                return 2

        config_dir = args.config_dir
        if (
            config_dir is None
            and preset_data
            and preset_data.get("config_dir") is not None
        ):
            config_dir = preset_data["config_dir"]

        try:
            cfg = load_pipeline_config(config_dir)
        except ConfigError as exc:
            print(f"Config error: {exc}")
            return 2

        profile = args.profile
        if profile is None:
            if not preset_data:
                print(
                    "Either --profile or --preset (with a profile field) is required."
                )
                return 2
            profile = preset_data["profile"]

        subtitle_style = args.subtitle_style
        if subtitle_style is None:
            if preset_data is not None:
                subtitle_style = preset_data["subtitle_style"]
            else:
                subtitle_style = "minimal"

        if profile not in cfg.encode_profiles:
            names = ", ".join(sorted(cfg.encode_profiles))
            print(
                f"Unsupported profile {profile!r}. "
                f"Valid encode profiles from {cfg.config_dir}: {names}."
            )
            return 2
        if subtitle_style not in cfg.subtitle_styles:
            styles = ", ".join(sorted(cfg.subtitle_styles))
            print(
                f"Unknown subtitle style {subtitle_style!r}. "
                f"Valid styles from {cfg.config_dir}: {styles}."
            )
            return 2

        job_preset_record = (
            str(preset_path.resolve()) if preset_path is not None else None
        )
        subtitle_font_size = args.subtitle_font_size
        if subtitle_font_size is None and preset_data is not None:
            preset_sf = preset_data.get("subtitle_font_size")
            if preset_sf is not None:
                subtitle_font_size = preset_sf
        if subtitle_font_size is None:
            try:
                subtitle_font_size = subtitle_font_size_from_environment()
            except ValueError as exc:
                print(f"Config error: {exc}")
                return 2

        return run_social_clipr_job(
            args.input,
            profile,
            pipeline_config=cfg,
            subtitle_style=subtitle_style,
            job_preset=job_preset_record,
            subtitle_font_size=subtitle_font_size,
            skip_transcribe=args.skip_transcribe,
            refresh_word_cues_from_segments=args.refresh_word_cues_from_segments,
            captions_from_segments=args.captions_from_segments,
        )

    parser.print_help()
    return 0
