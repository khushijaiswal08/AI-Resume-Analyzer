from fastapi.testclient import TestClient

from resume_analyzer.api import create_app
from resume_analyzer.config import Settings
from resume_analyzer.ratelimit import MAX_TRACKED_CLIENTS, RateLimiter, client_key
from tests.conftest import SAMPLE_RESUME


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_blocks_with_retry_after():
    clock = Clock()
    limiter = RateLimiter(3, 60, clock)
    assert [limiter.check("a") for _ in range(3)] == [None, None, None]
    retry = limiter.check("a")
    assert retry is not None and 1 <= retry <= 61
    assert limiter.check("b") is None  # other clients are independent


def test_window_slides():
    clock = Clock()
    limiter = RateLimiter(2, 60, clock)
    limiter.check("a")
    clock.now += 30
    limiter.check("a")
    assert limiter.check("a") is not None
    clock.now += 31  # the first hit has left the window
    assert limiter.check("a") is None
    assert limiter.check("a") is not None


def test_zero_disables_the_limit():
    limiter = RateLimiter(0, 60)
    assert all(limiter.check("a") is None for _ in range(100))


def test_memory_is_bounded():
    clock = Clock()
    limiter = RateLimiter(5, 600, clock)
    for number in range(MAX_TRACKED_CLIENTS + 50):
        clock.now += 0.001
        limiter.check(f"ip-{number}")
    assert len(limiter._hits) <= MAX_TRACKED_CLIENTS


def test_client_key_trusts_forwarded_header_only_when_told_to():
    assert client_key("1.2.3.4", "9.9.9.9, 5.6.7.8", trust_proxy=False) == "1.2.3.4"
    assert client_key("1.2.3.4", "9.9.9.9, 5.6.7.8", trust_proxy=True) == "5.6.7.8"  # last = ours
    assert client_key("1.2.3.4", None, trust_proxy=True) == "1.2.3.4"
    assert client_key(None, None, trust_proxy=False) == "unknown"


def make_client(**overrides) -> TestClient:
    settings = Settings(_env_file=None, gemini_api_key=None, **overrides)
    return TestClient(create_app(settings, llm_client=None))


def post(client, headers=None):
    return client.post(
        "/api/analyze", files={"resume": ("r.txt", SAMPLE_RESUME.encode())}, headers=headers or {}
    )


def test_api_returns_429_with_retry_after_and_json_detail():
    client = make_client(rate_limit_max=2)
    assert [post(client).status_code for _ in range(2)] == [200, 200]
    blocked = post(client)
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) >= 1
    assert "Too many analyses" in blocked.json()["detail"]
    assert client.get("/api/health").status_code == 200  # only analyses are limited


def test_api_limit_is_per_client_when_proxy_is_trusted():
    client = make_client(rate_limit_max=1, trust_proxy=True)
    assert post(client, {"X-Forwarded-For": "10.0.0.1"}).status_code == 200
    assert post(client, {"X-Forwarded-For": "10.0.0.2"}).status_code == 200
    assert post(client, {"X-Forwarded-For": "10.0.0.1"}).status_code == 429


def test_forged_forwarded_header_does_not_bypass_when_proxy_is_not_trusted():
    client = make_client(rate_limit_max=1)
    assert post(client, {"X-Forwarded-For": "10.0.0.1"}).status_code == 200
    assert post(client, {"X-Forwarded-For": "10.0.0.2"}).status_code == 429


def test_default_limit_is_20_per_10_minutes():
    settings = Settings(_env_file=None)
    assert (settings.rate_limit_max, settings.rate_limit_window_seconds) == (20, 600)
