"""transcript-tools: clean meeting transcripts (Zoom / MS Stream) for captions
and readable transcripts, with a project glossary and a guarded LLM polish."""

from importlib.resources import files

import yaml

from .core import (
    Cue,
    Glossary,
    apply_terms,
    parse,
    to_paragraphs,
    to_srt,
    to_transcript,
    to_vtt,
)

__version__ = "0.1.0"

__all__ = [
    "Cue",
    "Glossary",
    "apply_terms",
    "parse",
    "to_paragraphs",
    "to_srt",
    "to_transcript",
    "to_vtt",
    "default_glossary",
]


def default_glossary() -> Glossary:
    """Load the packaged PolicyEngine glossary."""
    data = yaml.safe_load((files(__package__) / "glossary.yaml").read_text("utf-8"))
    return Glossary.from_dict(data)
