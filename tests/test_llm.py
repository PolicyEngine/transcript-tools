from transcript_tools.llm import (
    guard,
    numbers,
    numbers_preserved,
    polish_paragraphs,
)


def test_numbers_extraction():
    got = numbers("GPT-5.5 hit 80.3% on $2,000, 100 households")
    assert got == sorted(["5.5", "80.3%", "$2,000", "100"])


def test_numbers_preserved():
    assert numbers_preserved("it was 80.3% of $2,000", "It was 80.3% of $2,000 exactly.")
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
