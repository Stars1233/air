"""Check Air's success and error paths through a local Worker."""

import argparse
import sys
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.request import urlopen


@dataclass(frozen=True)
class Expectation:
    """One Worker HTTP response to validate."""

    path: str
    status: int
    body_text: str | None


EXPECTATIONS = (
    Expectation("/", 200, None),
    Expectation("/missing", 404, "404 Not Found"),
    Expectation("/http-404", 404, "404 Not Found"),
    Expectation("/error", 500, "500 Internal Server Error"),
)


def fetch(url: str) -> tuple[int, str]:
    """Return a response status and body, including for HTTP errors."""
    try:
        response = urlopen(url, timeout=10)
    except HTTPError as error:
        return error.code, error.read().decode()
    with response:
        return response.status, response.read().decode()


def main() -> int:
    """Check all expected Worker routes."""
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", help="Local pywrangler dev URL")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    failed = False
    for expectation in EXPECTATIONS:
        status, body = fetch(f"{base_url}{expectation.path}")
        body_matches = expectation.body_text is None or expectation.body_text in body
        passed = status == expectation.status and body_matches
        result = "PASS" if passed else "FAIL"
        sys.stdout.write(f"{result} {expectation.path}: HTTP {status}\n")
        failed = failed or not passed

    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
