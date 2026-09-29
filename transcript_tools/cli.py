"""Command-line interface: ``clean-transcript input.vtt [options]``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from . import default_glossary
from .core import (
    Glossary,
    format_transcript,
    parse,
    to_paragraphs,
    to_srt,
    to_transcript,
    to_vtt,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clean-transcript",
        description="Clean a Zoom / MS Stream VTT (or SRT) into YouTube-ready "
        "captions and a readable transcript.",
    )
    p.add_argument("input", help="path to the .vtt or .srt transcript")
    p.add_argument("-o", "--out-dir", help="output directory (default: alongside input)")
    p.add_argument("-n", "--name", help="output basename (default: input stem)")
    p.add_argument(
        "-g",
        "--glossary",
        action="append",
        default=[],
        help="extra glossary YAML to layer on top of the default (repeatable)",
    )
    p.add_argument(
        "-s",
        "--speaker",
        action="append",
        default=[],
        metavar="FULL=LABEL",
        help='caption label override, e.g. "Jane Doe=Audience" (repeatable)',
    )
    p.add_argument("--title", default="", help="title line for the transcript")
    p.add_argument("--subtitle", default="", help="subtitle line for the transcript")
    p.add_argument("--no-captions", action="store_true", help="skip .srt/.vtt")
    p.add_argument("--no-transcript", action="store_true", help="skip .txt")
    p.add_argument(
        "--llm",
        action="store_true",
        help="polish the readable transcript with an LLM (guarded; needs the "
        "[llm] extra and ANTHROPIC_API_KEY)",
    )
    p.add_argument(
        "--model",
        default="claude-sonnet-5-5",
        help="model id for --llm; must accept the effort parameter "
        "(default: %(default)s)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    src = Path(args.input)
    if not src.exists():
        print(f"error: no such file: {src}", file=sys.stderr)
        return 2

    gloss: Glossary = default_glossary()
    for extra in args.glossary:
        gloss = gloss.merge(Glossary.from_dict(yaml.safe_load(Path(extra).read_text())))
    for spec in args.speaker:
        if "=" not in spec:
            print(f"error: --speaker needs FULL=LABEL, got {spec!r}", file=sys.stderr)
            return 2
        full, label = spec.split("=", 1)
        gloss.speakers[full.strip()] = label.strip()

    cues = parse(src.read_text("utf-8"))
    if not cues:
        print("error: no cues parsed — is this a VTT/SRT transcript?", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir) if args.out_dir else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.name or src.stem
    written: list[Path] = []

    if not args.no_captions:
        srt_path = out_dir / f"{stem}.srt"
        vtt_path = out_dir / f"{stem}.vtt"
        srt_path.write_text(to_srt(cues, gloss), "utf-8")
        vtt_path.write_text(to_vtt(cues, gloss), "utf-8")
        written += [srt_path, vtt_path]

    if not args.no_transcript:
        if args.llm:
            from .llm import polish_paragraphs

            paras = to_paragraphs(cues, gloss)
            skipped = []
            paras = polish_paragraphs(
                paras,
                model=args.model,
                on_skip=lambda spk, why: skipped.append((spk, why)),
            )
            txt = format_transcript(paras, title=args.title, subtitle=args.subtitle)
            if skipped:
                print(f"  (kept {len(skipped)} turn(s) unpolished by the guardrail)")
        else:
            txt = to_transcript(cues, gloss, title=args.title, subtitle=args.subtitle)
        txt_path = out_dir / f"{stem}-transcript.txt"
        txt_path.write_text(txt, "utf-8")
        written += [txt_path]

    speakers = sorted({c.speaker for c in cues if c.speaker})
    print(f"parsed {len(cues)} cues · speakers: {', '.join(speakers) or '—'}")
    for path in written:
        print(f"  wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
