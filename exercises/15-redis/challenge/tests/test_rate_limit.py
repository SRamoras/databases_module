import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rate_limit import (  # noqa: E402
    allow_request_fixed,
    allow_request_sliding,
    allow_request_sliding_not_atomic,
    r,
    sliding_key,
)

CUSTOMER = 4242
MINUTE = 29_000_000 * 60  # the start of some minute, in seconds since 1970


@pytest.fixture(autouse=True)
def clean():
    def delete():
        for key in r.scan_iter(f"ratelimit:*:{CUSTOMER}*"):
            r.delete(key)

    delete()
    yield
    delete()


def burst(allow) -> list[bool]:
    """10 requests at 59.0 ... 59.9 s of one minute, 10 at 0.0 ... 0.9 s of the next."""
    times = [MINUTE + 59 + i / 10 for i in range(10)] + [MINUTE + 60 + i / 10 for i in range(10)]
    return [allow(CUSTOMER, t) for t in times]


def test_fixed_window_accepts_20_across_the_minute_boundary():
    results = burst(allow_request_fixed)
    print(f"\nfixed:   {results.count(True)} accepted of 20 -> {results}")
    assert results.count(True) == 20


def test_sliding_window_accepts_only_10_in_any_60_seconds():
    results = burst(allow_request_sliding)
    print(f"\nsliding: {results.count(True)} accepted of 20 -> {results}")
    assert results.count(True) == 10
    assert results[:10] == [True] * 10 and results[10:] == [False] * 10


def test_sliding_window_accepts_again_after_60_seconds():
    for i in range(10):
        assert allow_request_sliding(CUSTOMER, MINUTE + i)
    assert not allow_request_sliding(CUSTOMER, MINUTE + 59.9)
    assert allow_request_sliding(CUSTOMER, MINUTE + 60.0)  # the request at MINUTE + 0 left the window
    assert not allow_request_sliding(CUSTOMER, MINUTE + 60.5)


def test_sliding_window_under_concurrency_accepts_exactly_10():
    start = threading.Barrier(10)
    now = MINUTE + 30.0  # every request at the same moment: the members must still be unique

    def client(_: int) -> list[bool]:
        start.wait()
        return [allow_request_sliding(CUSTOMER, now) for _ in range(3)]

    with ThreadPoolExecutor(10) as pool:
        results = [ok for batch in pool.map(client, range(10)) for ok in batch]

    print(f"\nconcurrent sliding: {len(results)} requests, {results.count(True)} accepted, "
          f"{r.zcard(sliding_key(CUSTOMER))} members in the sorted set")
    assert len(results) == 30
    assert results.count(True) == 10
    assert r.zcard(sliding_key(CUSTOMER)) == 10


def test_check_then_add_in_separate_commands_breaks_the_limit():
    """Why the script is needed: two clients interleaved between ZCARD and ZADD."""
    for i in range(9):
        assert allow_request_sliding(CUSTOMER, MINUTE + i)

    results = {}
    # client B runs completely between client A's count and A's add
    a = allow_request_sliding_not_atomic(
        CUSTOMER, MINUTE + 20,
        between=lambda: results.setdefault("B", allow_request_sliding_not_atomic(CUSTOMER, MINUTE + 20)),
    )
    count = r.zcard(sliding_key(CUSTOMER))
    print(f"\nnot atomic: A {a}, B {results['B']}, {count} requests in the window (limit 10)")
    assert a and results["B"]
    assert count == 11
