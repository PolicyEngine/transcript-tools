from transcript_tools.cli import _build_parser


def test_default_llm_model():
    assert _build_parser().parse_args(["x.vtt"]).model == "claude-sonnet-5-5"


def test_model_override():
    args = _build_parser().parse_args(["x.vtt", "--model", "claude-opus-5-5"])
    assert args.model == "claude-opus-5-5"
