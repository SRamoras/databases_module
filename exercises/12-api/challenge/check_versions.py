"""Task 3: a change made through one version must be visible in the other.

    uv run python check_versions.py            # both versions (after expand)
    uv run python check_versions.py v2         # only version 2 (after contract)

V1_URL and V2_URL default to http://127.0.0.1:8001 and http://127.0.0.1:8002.
Exits with 1 if any check fails.
"""

import os
import sys
import time

import httpx

V1 = os.environ.get("V1_URL", "http://127.0.0.1:8001")
V2 = os.environ.get("V2_URL", "http://127.0.0.1:8002")
CUSTOMER = 1
failures = 0


def show(label: str, response: httpx.Response) -> dict:
    print(f"{label}: {response.status_code} {response.text}")
    return response.json() if response.status_code == 200 else {}


def check(condition: bool, message: str) -> None:
    global failures
    print(f"  {'OK  ' if condition else 'FAIL'} {message}")
    failures += not condition


def write_then_read(writer: str, reader: str) -> None:
    name = "v1" if writer == V1 else "v2"
    email = f"{name}-{int(time.time() * 1000)}@example.org"
    show(f"PUT {writer}/customers/{CUSTOMER}/email", httpx.put(
        f"{writer}/customers/{CUSTOMER}/email", json={"email": email}))
    got = show(f"GET {reader}/customers/{CUSTOMER}", httpx.get(f"{reader}/customers/{CUSTOMER}"))
    check(got.get("email") == email, f"{reader} sees {email}")


def main() -> int:
    if sys.argv[1:] == ["v2"]:
        write_then_read(V2, V2)
    else:
        print("== written by v1 (email), read by v2 (email_address)")
        write_then_read(V1, V2)
        print("== written by v2 (email_address), read by v1 (email)")
        write_then_read(V2, V1)
    print("all checks passed" if failures == 0 else f"{failures} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
