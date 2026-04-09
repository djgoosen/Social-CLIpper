"""Unit tests for normalized word-cue helpers."""

from __future__ import annotations

from social_clipr.word_cues import (
    MIN_SYNTHETIC_WORD_CUE_DURATION_SEC,
    count_stored_word_cues,
    normalize_word_cues,
)


def test_count_stored_word_cues_matches_from_word_cues_field() -> None:
    payload = {
        "word_cues": [
            {"start": 0.0, "end": 0.5, "text": "a"},
            {"start": 0.5, "end": 1.0, "text": "b"},
        ],
        "segments": [{"start": 0.0, "end": 1.0, "text": "x y z"}],
    }
    assert count_stored_word_cues(payload) == 2


def test_normalize_word_cues_prefers_explicit_word_cues_field() -> None:
    payload = {
        "word_cues": [
            {"start": 0.0, "end": 0.4, "text": "hello"},
            {"start": 0.4, "end": 1.0, "text": "world"},
        ],
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "ignored segment"},
        ],
    }
    cues = normalize_word_cues(payload)
    assert [cue.text for cue in cues] == ["hello", "world"]
    assert cues[0].start == 0.0 and cues[1].end == 1.0


def test_normalize_word_cues_reads_words_from_segments() -> None:
    payload = {
        "segments": [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "ignored",
                "words": [
                    {"start": 0.0, "end": 0.3, "text": "alpha"},
                    {"start": 0.3, "end": 1.0, "text": "beta"},
                ],
            }
        ]
    }
    cues = normalize_word_cues(payload)
    assert [cue.text for cue in cues] == ["alpha", "beta"]


def test_normalize_word_cues_accepts_whisper_word_field() -> None:
    payload = {
        "segments": [
            {
                "start": 0.0,
                "end": 1.0,
                "text": "x",
                "words": [
                    {"word": " alpha", "start": 0.0, "end": 0.5},
                    {"word": " beta", "start": 0.5, "end": 1.0},
                ],
            }
        ]
    }
    cues = normalize_word_cues(payload)
    assert [cue.text for cue in cues] == ["alpha", "beta"]


def test_normalize_word_cues_splits_segments_when_word_timings_missing() -> None:
    payload = {
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "one two"},
        ]
    }
    cues = normalize_word_cues(payload)
    assert [cue.text for cue in cues] == ["one", "two"]
    assert cues[0].start == 0.0
    assert cues[0].end == 1.0
    assert cues[1].start == 1.0
    assert cues[1].end == 2.0


def test_normalize_word_cues_packs_short_segment_to_min_word_duration() -> None:
    m = MIN_SYNTHETIC_WORD_CUE_DURATION_SEC
    payload = {
        "segments": [
            {"start": 0.0, "end": 0.2, "text": "a b c"},
        ]
    }
    cues = normalize_word_cues(payload)
    assert [cue.text for cue in cues] == ["a", "b", "c"]
    assert cues[0].start == 0.0 and cues[0].end == m
    assert cues[1].start == m and cues[1].end == 2 * m
    assert cues[2].start == 2 * m and cues[2].end == 0.2


def test_normalize_word_cues_starved_segment_uses_proportional_non_overlapping() -> (
    None
):
    payload = {
        "segments": [
            {"start": 0.0, "end": 0.15, "text": "a b c"},
        ]
    }
    cues = normalize_word_cues(payload)
    assert [cue.text for cue in cues] == ["a", "b", "c"]
    step = 0.15 / 3
    assert cues[0].start == 0.0 and abs(cues[0].end - step) < 1e-9
    assert abs(cues[1].start - step) < 1e-9 and abs(cues[1].end - 2 * step) < 1e-9
    assert abs(cues[2].start - 2 * step) < 1e-9 and cues[2].end == 0.15


def test_normalize_word_cues_zero_span_segment_collapses_to_single_readable_cue() -> (
    None
):
    payload = {
        "segments": [
            {"start": 1.0, "end": 1.0, "text": "no time"},
        ]
    }
    cues = normalize_word_cues(payload)
    assert len(cues) == 1
    assert cues[0].text == "no time"
    assert cues[0].start == 1.0
    assert cues[0].end == 1.0 + MIN_SYNTHETIC_WORD_CUE_DURATION_SEC
