from office_agent.script_sandbox import truncate_output


def test_truncate_output_under_cap() -> None:
    text, cut = truncate_output("hello", cap=100)
    assert text == "hello"
    assert cut is False


def test_truncate_output_over_cap() -> None:
    text, cut = truncate_output("abcdefghij", cap=4)
    assert cut is True
    assert "truncated" in text
    assert text.startswith("abcd") or text.startswith("abc")
