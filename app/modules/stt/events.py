"""One vocabulary for what the recognisers say, and the assembler that turns it into customer turns.

The providers mean different things by similar words, so nothing here pretends they are the same:

- `partial`        an interim guess for the segment being spoken. It REPLACES the previous partial, never appends.
- `final`          a finished piece of text (Speechmatics AddSegment/AddTranscript, Soniox final tokens, ElevenLabs
                   committed_transcript). One final is not a finished turn: a turn can hold several.
- `speech_started` / `speech_ended`   voice activity, not finished thoughts.
- `turn_started` / `turn_ended`       the component that owns turn-taking says the customer is done. `source` says
                   whether the PROVIDER sent it or we DERIVED it locally (and from what) – never blur the two.

Exactly one component closes a turn in a given profile (`profiles.Profile.turn_owner`); the assembler closes a turn
only on `turn_ended` or an explicit `close()` from that owner, so two endpointers cannot answer the same input twice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KINDS = ("partial", "final", "speech_started", "speech_ended", "turn_started", "turn_ended", "error", "status")


@dataclass
class SttEvent:
    kind: str
    text: str = ""
    at: float = 0.0                       # seconds on the WALL clock since the session started (our timeline)
    audio_start: float | None = None      # seconds on the AUDIO timeline (the recording), when the provider says
    audio_end: float | None = None
    source: str = "provider"              # "provider" | "derived:<what it was derived from>"
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self, with_raw: bool = True) -> dict:
        d = {"kind": self.kind, "text": self.text, "at": round(self.at, 3), "audio_start": self.audio_start,
             "audio_end": self.audio_end, "source": self.source}
        if with_raw:
            d["raw"] = self.raw
        return d


@dataclass
class Turn:
    segments: list[str] = field(default_factory=list)
    spans: list[tuple[float | None, float | None]] = field(default_factory=list)
    closed_by: str = ""                   # "provider" | "derived:..." | "external" (our flush) | "end_of_stream"
    late: list[str] = field(default_factory=list)  # finals that arrived after the turn closed but belong to it
    first_partial_at: float | None = None
    first_final_at: float | None = None
    closed_at: float | None = None

    @property
    def text(self) -> str:
        return " ".join(t for t in [*self.segments, *self.late] if t).strip()


class TurnAssembler:
    """Feed it SttEvents in arrival order; read `turns` and `partial`.

    Guarantees (tested): partials replace; several finals in one turn keep their order; a final delivered twice
    (same text and audio span) counts once; a turn_ended with nothing in it makes no turn; a final that arrives late
    for audio the last turn already covered is attached to that turn instead of starting a phantom one.
    """

    EPS = 0.05

    def __init__(self) -> None:
        self.turns: list[Turn] = []
        self.partial: str = ""
        self._open = Turn()
        self._seen: set[tuple] = set()
        self._closed_audio_end: float | None = None

    @property
    def open_text(self) -> str:
        t = self._open.text
        return (t + " " + self.partial).strip() if self.partial else t

    def feed(self, ev: SttEvent) -> Turn | None:
        """Returns the turn this event closed, if any."""
        if ev.kind == "partial":
            self.partial = ev.text.strip()
            if self._open.first_partial_at is None and self.partial:
                self._open.first_partial_at = ev.at
            return None
        if ev.kind == "final":
            text = ev.text.strip()
            if not text:
                return None
            key = (text, ev.audio_start, ev.audio_end)
            if ev.audio_start is not None and key in self._seen:
                return None  # redelivered
            self._seen.add(key)
            if (self.turns and ev.audio_end is not None and self._closed_audio_end is not None
                    and ev.audio_end <= self._closed_audio_end + self.EPS and not self._open.segments):
                self.turns[-1].late.append(text)
                return None
            self.partial = ""
            self._open.segments.append(text)
            self._open.spans.append((ev.audio_start, ev.audio_end))
            if self._open.first_final_at is None:
                self._open.first_final_at = ev.at
            return None
        if ev.kind == "turn_ended":
            return self.close(ev.source, at=ev.at)
        return None

    def close(self, closed_by: str, at: float | None = None) -> Turn | None:
        """Close the open turn (the owner said so, or the stream ended). Empty turns are dropped."""
        if not self._open.segments:
            if self.partial and closed_by == "end_of_stream":  # nothing finalised: keep what we heard, marked
                self._open.segments.append(self.partial)
            else:
                self.partial = ""
                return None
        t = self._open
        t.closed_by, t.closed_at = closed_by, at
        ends = [e for _, e in t.spans if e is not None]
        if ends:
            self._closed_audio_end = max(ends)
        self.turns.append(t)
        self._open, self.partial = Turn(), ""
        return t

    @property
    def text(self) -> str:
        """All finished customer text in order, plus anything still open."""
        parts = [t.text for t in self.turns]
        if self.open_text:
            parts.append(self.open_text)
        return " ".join(parts).strip()
