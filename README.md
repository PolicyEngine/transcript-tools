# transcript-tools

Turn a raw meeting transcript (Zoom or Microsoft Stream `.vtt`, or an `.srt`)
into **YouTube-ready captions** and a **readable transcript** — with a project
glossary that fixes domain terms, and an optional, *guarded* LLM polish.

Built for PolicyEngine webinars and talks, but the glossary is just a file, so
it works for any project.

## Why

Auto-transcripts get the easy 95% and fumble exactly the words that matter:
"Policy Engine" instead of `PolicyEngine`, "GPT 5.5" instead of `GPT-5.5`,
"policy bench" instead of `PolicyBench`. Generic cleaners strip filler but
don't know your vocabulary. This does both — and keeps two outputs that serve
different jobs:

| Output | File | Treatment |
| --- | --- | --- |
| **Captions** | `<name>.srt`, `<name>.vtt` | **Verbatim.** Only the glossary is applied, so they stay in sync with the audio. Speaker labels are added on speaker change. |
| **Transcript** | `<name>-transcript.txt` | **Readable.** Merged by speaker, filler removed, re-capitalized sentence-aware. For the video description, show notes, or a blog. |

## Install

```bash
uv tool install git+https://github.com/PolicyEngine/transcript-tools
# or, in a project:
uv pip install git+https://github.com/PolicyEngine/transcript-tools
```

## Use

```bash
clean-transcript GMT20260625-Recording.transcript.vtt
```

Writes `GMT20260625-Recording.transcript.srt`, `.vtt`, and
`...-transcript.txt` next to the input. Then upload the `.srt` in YouTube
Studio → your video → Subtitles → Add.

Common options:

```bash
# custom output name + directory
clean-transcript in.vtt -n policybench-webinar -o ./captions

# anonymize an audience member in both outputs
clean-transcript in.vtt -s "Jane Doe=Audience"

# add a per-talk glossary on top of the default (one-off names / mishears)
clean-transcript in.vtt -g this-talk.yaml

# title the readable transcript
clean-transcript in.vtt --title "PolicyBench webinar" --subtitle "June 25, 2026"
```

## Glossary

The packaged [`glossary.yaml`](transcript_tools/glossary.yaml) holds the
PolicyEngine vocabulary. Layer your own with `-g/--glossary` (it merges on
top, yours wins):

```yaml
terms:                                   # applied to captions AND transcript
  - { pattern: '[Pp]olicy\s+[Ee]ngine', replace: PolicyEngine }
filler:                                  # removed from the transcript only
  - you know
proper_nouns: [PolicyEngine, GPT, SNAP]  # keep caps mid-sentence
speakers: { "Jane Doe": "Audience" }     # caption label override
```

`terms` are deterministic regex replacements — safe enough to run on the
verbatim captions. Keep one-off, talk-specific corrections in a `-g` file so
the default glossary stays general.

## Optional: LLM polish

The deterministic transcript is good. For publication-grade prose (it stitches
Zoom's sentence fragments back together), add `--llm`:

```bash
uv pip install 'transcript-tools[llm]'
export ANTHROPIC_API_KEY=...
clean-transcript in.vtt --llm
```

It cleans each speaker turn, **but never silently changes facts**: a guardrail
rejects any polished turn that alters a number, dollar amount, or percentage
(or balloons the text), falling back to the deterministic version and telling
you how many turns it kept. Captions are never sent to the model.

## Develop

```bash
uv run --extra dev pytest
```

## Prior art

For generic, glossary-free cleanup there are good tools already —
[clean-transcribe](https://github.com/itsmevictor/clean-transcribe) (LLM-based,
can re-transcribe from audio), and simple strippers like
[VTTCleaner](https://github.com/SandeepShenoy72/VTTCleaner). This repo exists
for the parts they don't cover: a project glossary, the captions-vs-transcript
split, and a fact-preserving guardrail on the LLM pass.

## License

MIT
