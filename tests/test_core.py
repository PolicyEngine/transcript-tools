from transcript_tools import default_glossary
from transcript_tools.core import (
    Glossary,
    apply_terms,
    parse,
    to_srt,
    to_transcript,
    to_vtt,
)

SAMPLE_VTT = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
Max Ghenis: Hello, this is policy engine and policy bench.

2
00:00:03.000 --> 00:00:05.000
Max Ghenis: GPT 5.5 is, you know, the best, sort of.

3
00:00:05.000 --> 00:00:07.000
Pavel Makarchuk: Yeah, the the results are clear.
"""


def test_parse_extracts_speaker_and_timestamp():
    cues = parse(SAMPLE_VTT)
    assert len(cues) == 3
    assert cues[0].speaker == "Max Ghenis"
    assert cues[0].start == "00:00:01.000"
    assert "policy engine" in cues[0].text


def test_parse_handles_srt_with_comma_timestamps():
    srt = "1\n00:00:01,000 --> 00:00:02,000\nMax Ghenis: Hi there.\n"
    cues = parse(srt)
    assert len(cues) == 1
    assert cues[0].start == "00:00:01.000"
    assert cues[0].text == "Hi there."


def test_apply_terms_fixes_brand_and_model():
    g = default_glossary()
    out = apply_terms("policy engine and policy bench, GPT 5.5", g)
    assert "PolicyEngine" in out
    assert "PolicyBench" in out
    assert "GPT-5.5" in out
    assert "policy engine" not in out


def test_srt_is_verbatim_with_speaker_on_change():
    g = default_glossary()
    srt = to_srt(parse(SAMPLE_VTT), g)
    assert "00:00:01,000 --> 00:00:03,000" in srt  # comma timestamps
    assert "Max: Hello" in srt
    assert srt.count("Max:") == 1  # not repeated on the second Max cue
    assert "Pavel: Yeah" in srt  # labelled on speaker change
    assert "you know" in srt  # captions keep filler (sync)
    assert "PolicyEngine" in srt  # but glossary still applies


def test_vtt_has_header_and_terms():
    g = default_glossary()
    vtt = to_vtt(parse(SAMPLE_VTT), g)
    assert vtt.startswith("WEBVTT")
    assert "PolicyEngine" in vtt and "PolicyBench" in vtt


def test_transcript_removes_filler_collapses_repeats_and_merges():
    g = default_glossary()
    txt = to_transcript(parse(SAMPLE_VTT), g)
    assert "you know" not in txt.lower()
    assert "sort of" not in txt.lower()
    assert "the the" not in txt
    assert txt.count("Max Ghenis:") == 1
    assert txt.count("Pavel Makarchuk:") == 1


def test_transcript_is_sentence_aware():
    g = default_glossary()
    vtt = (
        "WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.000\nMax Ghenis: We took 100 households\n"
        "\n2\n00:00:02.000 --> 00:00:03.000\nMax Ghenis: And asked the models.\n"
    )
    txt = to_transcript(parse(vtt), g)
    # second cue is mid-sentence -> "And" lowercased to join cleanly
    assert "households and asked" in txt


def test_speaker_override_via_glossary_merge():
    g = default_glossary().merge(
        Glossary.from_dict({"speakers": {"Pavel Makarchuk": "Audience"}})
    )
    srt = to_srt(parse(SAMPLE_VTT), g)
    assert "Audience: Yeah" in srt
    assert "Pavel:" not in srt
