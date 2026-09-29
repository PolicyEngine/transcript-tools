import json
from types import SimpleNamespace

import pytest

from transcript_tools.llm import (
    guard,
    numbers,
    numbers_preserved,
    polish_paragraphs,
    polish_turn,
)


def test_numbers_extraction():
    got = numbers("GPT-5.5 hit 80.3% on $2,000, 100 households")
    assert got == sorted(["5.5", "80.3%", "$2,000", "100"])


def test_numbers_preserved():
    assert numbers_preserved(
        "it was 80.3% of $2,000", "It was 80.3% of $2,000 exactly."
    )
    assert not numbers_preserved("80.3%", "80.4%")


def test_guard_rejects_changed_numbers():
    ok, why = guard("we got 80.3%", "we got 80.4%")
    assert not ok
    assert "number" in why


def test_guard_rejects_empty_and_overlong():
    assert not guard("hi", "")[0]
    assert not guard("a" * 10, "b" * 100)[0]


def test_guard_accepts_clean_polish():
    ok, _ = guard("um, we, you know, got 80.3%", "We got 80.3%.")
    assert ok


def test_polish_keeps_original_when_numbers_change():
    paras = [("Max", "we got 80.3% on $2,000")]
    skipped = []
    out = polish_paragraphs(
        paras,
        model="x",
        polish_fn=lambda t: "We got 80.4% on $2,000.",  # corrupts a number
        on_skip=lambda s, w: skipped.append((s, w)),
    )
    assert out == paras
    assert skipped and skipped[0][1] == "numbers changed"


def test_polish_applies_clean_result():
    paras = [("Max", "um we got, 80.3% on $2,000")]
    out = polish_paragraphs(
        paras, model="x", polish_fn=lambda t: "We got 80.3% on $2,000."
    )
    assert out == [("Max", "We got 80.3% on $2,000.")]


def test_polish_survives_polish_fn_errors():
    paras = [("Max", "keep me 50%")]

    def boom(_):
        raise RuntimeError("api down")

    out = polish_paragraphs(paras, model="x", polish_fn=boom)
    assert out == paras  # original preserved on error


class _FakeMessages:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.resp


def _fake_client(stop_reason="end_turn", text="We got 80.3%."):
    content = [
        SimpleNamespace(type="thinking", thinking="", signature="sig"),
        SimpleNamespace(type="text", text=text),
    ]
    resp = SimpleNamespace(stop_reason=stop_reason, content=content)
    return SimpleNamespace(messages=_FakeMessages(resp))


def test_polish_turn_request_shape():
    client = _fake_client()
    out = polish_turn("um we got 80.3%", model="claude-sonnet-5-5", client=client)
    assert out == "We got 80.3%."  # thinking blocks are skipped
    (kwargs,) = client.messages.calls
    assert kwargs["model"] == "claude-sonnet-5-5"
    assert kwargs["max_tokens"] >= 16000
    assert kwargs["output_config"] == {"effort": "low"}
    # Rejected (400) or unsupported on current Claude models.
    for banned in ("temperature", "top_p", "top_k", "thinking", "tool_choice"):
        assert banned not in kwargs
    # No assistant prefill: the only message is the user's turn.
    assert [m["role"] for m in kwargs["messages"]] == ["user"]


# Every stop_reason in anthropic.types.StopReason (anthropic 1.0-1.9).
STOP_REASONS = [
    "end_turn",
    "max_tokens",
    "stop_sequence",
    "tool_use",
    "pause_turn",
    "refusal",
    "model_context_window_exceeded",
]


@pytest.mark.parametrize("stop_reason", STOP_REASONS)
def test_only_complete_responses_are_used(stop_reason):
    paras = [("Max", "um we got, 80.3% on $2,000")]
    client = _fake_client(stop_reason=stop_reason, text="We got 80.3% on $2,000.")
    skipped = []
    out = polish_paragraphs(
        paras,
        model="claude-sonnet-5-5",
        polish_fn=lambda t: polish_turn(t, model="claude-sonnet-5-5", client=client),
        on_skip=lambda s, w: skipped.append((s, w)),
    )
    if stop_reason == "end_turn":
        assert out == [("Max", "We got 80.3% on $2,000.")]
        assert not skipped
    else:
        # A refusal or cut-off keeps the deterministic turn, even when the
        # partial text would pass the number guard.
        assert out == paras
        assert skipped == [
            ("Max", f"error: incomplete response (stop_reason={stop_reason})")
        ]


@pytest.mark.parametrize("stop_reason", ["end_turn", "refusal"])
def test_polish_turn_against_real_sdk(stop_reason):
    """The installed SDK sends the request shape and parses the reply (no network)."""
    anthropic = pytest.importorskip("anthropic")
    import httpx2  # the HTTP layer of anthropic>=1.0

    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx2.Response(
            200,
            json={
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-5-5",
                "content": [
                    {"type": "thinking", "thinking": "", "signature": "sig"},
                    {"type": "text", "text": "We got 80.3%."},
                ],
                "stop_reason": stop_reason,
                "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )

    client = anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(
            transport=httpx2.MockTransport(handler)
        ),
    )
    if stop_reason == "end_turn":
        out = polish_turn("um we got 80.3%", model="claude-sonnet-5-5", client=client)
        assert out == "We got 80.3%."
    else:
        with pytest.raises(RuntimeError, match="stop_reason=refusal"):
            polish_turn("um we got 80.3%", model="claude-sonnet-5-5", client=client)
    (body,) = sent
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == 16000
    assert body["output_config"] == {"effort": "low"}
    assert not {"temperature", "top_p", "top_k", "thinking", "tool_choice"} & set(body)
    assert [m["role"] for m in body["messages"]] == ["user"]
