from office_agent.config import merge_allowed_hosts


def test_merge_adds_api_base_host_and_local_defaults():
    assert merge_allowed_hosts("https://api.deepseek.com/v1", []) == [
        "127.0.0.1",
        "localhost",
        "api.deepseek.com",
    ]


def test_merge_keeps_existing_and_dedupes():
    result = merge_allowed_hosts(
        "http://10.0.0.8:8000/v1",
        ["10.0.0.8", "localhost", "custom.internal"],
    )
    assert result == ["127.0.0.1", "localhost", "10.0.0.8", "custom.internal"]


def test_merge_skips_missing_hostname():
    assert merge_allowed_hosts("not-a-url", ["other.example"]) == [
        "127.0.0.1",
        "localhost",
        "other.example",
    ]
