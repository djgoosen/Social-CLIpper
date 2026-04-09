"""Helpers for normalized word-level caption timing cues."""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Minimum duration for synthetic (equal-split / packed) word cues only; engine timings unchanged.
MIN_SYNTHETIC_WORD_CUE_DURATION_SEC = 0.08


@dataclass(frozen=True)
class WordCue:
    start: float
    end: float
    text: str


def _clean_text(value: object) -> str:
    return str(value).strip()


def _from_word_cues_field(payload: dict[str, object]) -> list[WordCue]:
    raw = payload.get("word_cues")
    if not isinstance(raw, list):
        return []
    cues: list[WordCue] = []
    for cue in raw:
        if not isinstance(cue, dict):
            continue
        try:
            text = _clean_text(cue.get("text", ""))
            if not text:
                continue
            cues.append(
                WordCue(
                    start=float(cue["start"]),
                    end=float(cue["end"]),
                    text=text,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return cues


def _split_segment_to_words(segment: dict[str, object]) -> list[WordCue]:
    text = _clean_text(segment.get("text", ""))
    if not text:
        return []
    words = [word for word in text.split() if word]
    if not words:  # pragma: no cover
        return []  # pragma: no cover
    try:
        start = float(segment["start"])
        end = float(segment["end"])
    except (KeyError, TypeError, ValueError):
        return []
    if end < start:
        start, end = end, start
    span = end - start
    n = len(words)
    min_d = MIN_SYNTHETIC_WORD_CUE_DURATION_SEC

    if n == 1:
        if span <= 0.0:
            return [
                WordCue(
                    start=start,
                    end=start + min_d,
                    text=words[0],
                )
            ]
        return [WordCue(start=start, end=end, text=words[0])]

    if span <= 0.0:
        return [WordCue(start=start, end=start + min_d, text=text)]

    # Deterministic equal split when each slice is already >= min duration.
    step = span / n
    if step >= min_d:
        cues: list[WordCue] = []
        cursor = start
        for idx, word in enumerate(words):
            next_cursor = end if idx == n - 1 else cursor + step
            cues.append(WordCue(start=cursor, end=next_cursor, text=word))
            cursor = next_cursor
        return cues

    # Short segment: pack first (n-1) words at min_d when the segment can afford it.
    if (n - 1) * min_d <= span:
        cues_pack: list[WordCue] = []
        cursor = start
        for idx, word in enumerate(words):
            if idx == n - 1:
                cues_pack.append(WordCue(start=cursor, end=end, text=word))
            else:
                nxt = cursor + min_d
                cues_pack.append(WordCue(start=cursor, end=nxt, text=word))
                cursor = nxt
        return cues_pack

    # Starved: cannot give min_d to all gaps; non-overlapping proportional split.
    cues_prop: list[WordCue] = []
    cursor = start
    for idx, word in enumerate(words):
        next_cursor = end if idx == n - 1 else cursor + step
        cues_prop.append(WordCue(start=cursor, end=next_cursor, text=word))
        cursor = next_cursor
    return cues_prop


def _from_segment_words(payload: dict[str, object]) -> list[WordCue]:
    raw = payload.get("segments")
    if not isinstance(raw, list):
        return []
    cues: list[WordCue] = []
    for segment in raw:
        if not isinstance(segment, dict):
            continue
        added_from_words = False
        raw_words = segment.get("words")
        if isinstance(raw_words, list):
            for word in raw_words:
                if not isinstance(word, dict):
                    continue
                try:
                    text = _clean_text(word.get("text", word.get("word", "")))
                    if not text:
                        continue
                    cues.append(
                        WordCue(
                            start=float(word["start"]),
                            end=float(word["end"]),
                            text=text,
                        )
                    )
                    added_from_words = True
                except (KeyError, TypeError, ValueError):
                    continue
            if added_from_words:
                continue
        cues.extend(_split_segment_to_words(segment))
    return cues


def count_stored_word_cues(payload: dict[str, object]) -> int:
    """How many cues are read from the ``word_cues`` field (same rules as caption path)."""
    return len(_from_word_cues_field(payload))


def normalize_word_cues(payload: dict[str, object]) -> list[WordCue]:
    """Return a normalized word-cue list from transcript payload variants."""
    direct = _from_word_cues_field(payload)
    if direct:
        return direct
    return _from_segment_words(payload)


def serialize_word_cues(cues: list[WordCue]) -> list[dict[str, object]]:
    return [asdict(cue) for cue in cues]
