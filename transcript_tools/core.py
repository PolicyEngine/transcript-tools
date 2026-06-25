"""Parse, clean, and emit meeting transcripts (Zoom / MS Stream VTT, or SRT).

Two distinct outputs, on purpose:

* **Captions** (``.srt`` / ``.vtt``) stay *verbatim* — only the glossary is
  applied — so they keep tracking the spoken audio and stay in sync.
* The **readable transcript** (``.txt``) is merged by speaker, has filler
  removed, and is re-capitalized sentence-aware for comfortable reading.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

_TS = re.compile(r"(\d{1,2}:\d{2}:\d{2})[.,](\d{1,3})")
_SPEAKER = re.compile(r"^([A-Z][\w.''-]*(?:\s+[A-Z][\w.''-]*){0,3}):\s*(.*)$", re.S)


@dataclass
class Cue:
    start: str  # normalized to HH:MM:SS.mmm
    end: str
    speaker: str | None
    text: str


def _norm_ts(ts: str) -> str:
    """Normalize a VTT/SRT timestamp to ``HH:MM:SS.mmm``."""
    m = _TS.search(ts)
    if not m:
        return ts.strip()
    return f"{m.group(1)}.{m.group(2):0<3}"


def parse(content: str) -> list[Cue]:
    """Parse VTT or SRT text into cues. Speaker is extracted from a leading
    ``Name:`` prefix when present (Zoom / MS Stream convention)."""
    cues: list[Cue] = []
    for block in re.split(r"\r?\n\r?\n", content):
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        ts_line = next((ln for ln in lines if "-->" in ln), None)
        if not ts_line:
            continue
        idx = lines.index(ts_line)
        left, right = ts_line.split("-->")
        start = _norm_ts(left)
        end = _norm_ts(right.strip().split()[0] if right.strip() else right)
        text = " ".join(ln.strip() for ln in lines[idx + 1 :]).strip()
        speaker = None
        m = _SPEAKER.match(text)
        if m:
            speaker, text = m.group(1).strip(), m.group(2).strip()
        if text:
            cues.append(Cue(start, end, speaker, text))
    return cues


# --------------------------------------------------------------------------- #
# Glossary
# --------------------------------------------------------------------------- #


@dataclass
class Glossary:
    terms: list[tuple[str, str]] = field(default_factory=list)  # (regex, replace)
    filler: list[str] = field(default_factory=list)
    proper_nouns: list[str] = field(default_factory=list)
    speakers: dict[str, str] = field(default_factory=dict)  # full -> caption label

    @classmethod
    def from_dict(cls, d: dict) -> "Glossary":
        terms = [(t["pattern"], t["replace"]) for t in d.get("terms", [])]
        return cls(
            terms=terms,
            filler=list(d.get("filler", [])),
            proper_nouns=list(d.get("proper_nouns", [])),
            speakers=dict(d.get("speakers", {})),
        )

    def merge(self, other: "Glossary") -> "Glossary":
        """Return a new glossary with ``other`` layered on top (other wins)."""
        return Glossary(
            terms=self.terms + other.terms,
            filler=sorted(set(self.filler) | set(other.filler)),
            proper_nouns=sorted(set(self.proper_nouns) | set(other.proper_nouns)),
            speakers={**self.speakers, **other.speakers},
        )

    def proper_re(self) -> re.Pattern:
        words = sorted(self.proper_nouns, key=len, reverse=True) or ["\0"]
        return re.compile(r"^(?:" + "|".join(re.escape(w) for w in words) + r")\b")

    def filler_re(self) -> re.Pattern | None:
        if not self.filler:
            return None
        alts = "|".join(re.escape(f) for f in self.filler)
        return re.compile(r",?\s*\b(?:" + alts + r")\b\s*,?", re.IGNORECASE)


def apply_terms(text: str, gloss: Glossary) -> str:
    for pat, rep in gloss.terms:
        text = re.sub(pat, rep, text)
    return text


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def first_name(full: str, gloss: Glossary) -> str:
    if full in gloss.speakers:
        return gloss.speakers[full]
    return full.split()[0] if full else full


def _squeeze(text: str) -> str:
    text = re.sub(r"\s+([,.;:?!])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _collapse_repeats(text: str) -> str:
    # "the the", "and, and", "we… we"
    text = re.sub(r"\b(\w+)\b[\s,…]+\1\b", r"\1", text, flags=re.IGNORECASE)
    # "the whole the whole"
    text = re.sub(r"\b(\w+\s+\w+)\s+\1\b", r"\1", text, flags=re.IGNORECASE)
    return text


def _append_chunk(buf: str, t: str, proper: re.Pattern) -> str:
    """Append a cue to a running paragraph with sentence-aware capitalization."""
    if not t:
        return buf
    starts = (not buf) or re.search(r"[.?!]['\"]?\s*$", buf)
    if starts:
        t = t[0].upper() + t[1:]
    elif not proper.match(t):  # mid-sentence, not a proper noun -> lowercase
        t = t[0].lower() + t[1:]
    return (buf + " " + t) if buf else t


# --------------------------------------------------------------------------- #
# Emit: captions (verbatim)
# --------------------------------------------------------------------------- #


def _caption_lines(cues: list[Cue], gloss: Glossary):
    prev = None
    for c in cues:
        text = _squeeze(apply_terms(c.text, gloss))
        label = ""
        spk = c.speaker or prev
        if c.speaker and c.speaker != prev:
            label = first_name(c.speaker, gloss) + ": "
        prev = spk
        yield c, (label + text)


def to_srt(cues: list[Cue], gloss: Glossary) -> str:
    out = []
    for i, (c, line) in enumerate(_caption_lines(cues, gloss), 1):
        s = c.start.replace(".", ",")
        e = c.end.replace(".", ",")
        out += [str(i), f"{s} --> {e}", line, ""]
    return "\n".join(out)


def to_vtt(cues: list[Cue], gloss: Glossary) -> str:
    out = ["WEBVTT", ""]
    for c, line in _caption_lines(cues, gloss):
        out += [f"{c.start} --> {c.end}", line, ""]
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Emit: readable transcript (polished)
# --------------------------------------------------------------------------- #


def to_paragraphs(cues: list[Cue], gloss: Glossary) -> list[tuple[str, str]]:
    """Merge consecutive same-speaker cues into clean paragraphs."""
    proper = gloss.proper_re()
    fre = gloss.filler_re()
    paras: list[tuple[str, str]] = []
    cur_spk, buf = None, ""
    for c in cues:
        spk = c.speaker or cur_spk or "Speaker"
        t = apply_terms(c.text, gloss)
        if fre:
            t = fre.sub(" ", t)
        t = _squeeze(_collapse_repeats(t).replace("…", " "))
        if not t:
            continue
        if spk != cur_spk and buf:
            paras.append((cur_spk, _squeeze(buf)))
            buf = ""
        cur_spk = spk
        buf = _append_chunk(buf, t, proper)
    if buf:
        paras.append((cur_spk, _squeeze(buf)))
    return paras


def format_transcript(
    paras: list[tuple[str, str]], *, title: str = "", subtitle: str = ""
) -> str:
    lines: list[str] = []
    if title:
        lines.append(title)
    if subtitle:
        lines.append(subtitle)
    if lines:
        lines.append("")
    for spk, txt in paras:
        lines.append(f"{spk}: {txt}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def to_transcript(
    cues: list[Cue], gloss: Glossary, *, title: str = "", subtitle: str = ""
) -> str:
    return format_transcript(
        to_paragraphs(cues, gloss), title=title, subtitle=subtitle
    )
