"""Optional LLM polish for the readable transcript.

This is **off by default**. When enabled it cleans each speaker turn into
readable prose, but it is wrapped in a hard guardrail: if the model changes
any number, dollar amount, or percentage — or balloons the text — the polish
is rejected and the deterministic version is kept. Cleaning must never invent
or alter facts.
"""

from __future__ import annotations

import re

_NUM = re.compile(r"\$?\d(?:[\d,]*\d)?(?:\.\d+)?%?")

_SYSTEM = (
    "You are cleaning up one speaker's turn from a verbatim webinar transcript "
    "so it reads well in print. Fix false starts, filler words, stutters, and "
    "run-on fragments into clean, readable sentences. HARD RULES: do not add, "
    "remove, or change any information; never change or drop a number, dollar "
    "amount, percentage, date, model name, program name, or proper noun; keep "
    "the speaker's meaning and voice; do not add commentary, headings, or "
    "preamble. Return ONLY the cleaned text."
)


def numbers(text: str) -> list[str]:
    """Sorted multiset of number-like tokens (for the guardrail)."""
    return sorted(m.group(0).strip(".,") for m in _NUM.finditer(text))


def numbers_preserved(original: str, polished: str) -> bool:
    return numbers(original) == numbers(polished)


def _client(api_key: str | None):
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - import guard
        raise RuntimeError(
            "LLM polish needs the 'anthropic' package. "
            "Install with: uv pip install 'transcript-tools[llm]'"
        ) from e
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def polish_turn(text: str, *, model: str, client) -> str:
    """Polish one turn via the Anthropic API. Returns raw model text."""
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=_SYSTEM,
        messages=[{"role": "user", "content": text}],
    )
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "".join(parts).strip()


def guard(original: str, polished: str) -> tuple[bool, str]:
    """Decide whether to accept a polished turn. Returns (ok, reason)."""
    if not polished:
        return False, "empty output"
    if not numbers_preserved(original, polished):
        return False, "numbers changed"
    if len(polished) > 1.5 * len(original) + 40:
        return False, "output too long (possible additions)"
    return True, "ok"


def polish_paragraphs(
    paras: list[tuple[str, str]],
    *,
    model: str,
    api_key: str | None = None,
    polish_fn=None,
    on_skip=None,
) -> list[tuple[str, str]]:
    """Polish each (speaker, text) turn, keeping the original on any guard fail.

    ``polish_fn`` is injectable for testing; by default it calls the API.
    ``on_skip(speaker, reason)`` is invoked when a turn is left unpolished.
    """
    if polish_fn is None:
        client = _client(api_key)

        def polish_fn(t):
            return polish_turn(t, model=model, client=client)

    out: list[tuple[str, str]] = []
    for spk, text in paras:
        try:
            cand = polish_fn(text)
        except Exception as e:  # network / API failure -> keep original
            cand, reason = "", f"error: {e}"
        else:
            ok, reason = guard(text, cand)
            if not ok:
                cand = ""
        if cand:
            out.append((spk, cand))
        else:
            if on_skip:
                on_skip(spk, reason)
            out.append((spk, text))
    return out
