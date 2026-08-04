import pytest
from starlette.requests import Request

import air
import air.form.csrf as csrf
from air.form import configure_csrf_secret


def _request_with_headers(*headers: tuple[str, str]) -> Request:
    raw_headers = [(b"host", b"example.test")]
    raw_headers.extend((name.lower().encode(), value.encode()) for name, value in headers)
    return Request({
        "type": "http",
        "method": "POST",
        "scheme": "https",
        "server": ("example.test", 443),
        "path": "/submit",
        "raw_path": b"/submit",
        "query_string": b"",
        "headers": raw_headers,
    })


def test_initial_secret_is_eager_on_threaded_runtimes(monkeypatch: pytest.MonkeyPatch) -> None:
    generated_secret = b"n" * 32
    calls: list[int] = []

    monkeypatch.delenv("AIRFORM_SECRET", raising=False)
    monkeypatch.setattr(csrf.sys, "platform", "linux")
    monkeypatch.setattr(
        csrf.secrets,
        "token_bytes",
        lambda length: calls.append(length) or generated_secret,
    )

    assert csrf._initial_secret() == generated_secret
    assert calls == [32]


def test_initial_secret_is_lazy_on_emscripten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIRFORM_SECRET", raising=False)
    monkeypatch.setattr(csrf.sys, "platform", "emscripten")

    def unexpected_entropy(_: int) -> bytes:
        msg = "entropy requested during import"
        raise AssertionError(msg)

    monkeypatch.setattr(csrf.secrets, "token_bytes", unexpected_entropy)

    assert csrf._initial_secret() is None


def test_initial_secret_prefers_configuration_on_emscripten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIRFORM_SECRET", "c" * 32)
    monkeypatch.setattr(csrf.sys, "platform", "emscripten")

    assert csrf._initial_secret() == b"c" * 32


@pytest.mark.parametrize("secret", ["", "short"])
def test_initial_secret_rejects_weak_configuration(monkeypatch: pytest.MonkeyPatch, secret: str) -> None:
    monkeypatch.setenv("AIRFORM_SECRET", secret)

    with pytest.raises(ValueError, match=r"must not be empty|at least 32 bytes"):
        csrf._initial_secret()


@pytest.mark.parametrize(
    ("secret", "expected"),
    [
        pytest.param("t" * 32, b"t" * 32, id="text-secret"),
        pytest.param(b"b" * 32, b"b" * 32, id="byte-secret"),
    ],
)
def test_configure_csrf_secret_accepts_text_or_bytes(
    monkeypatch: pytest.MonkeyPatch,
    secret: str | bytes,
    expected: bytes,
) -> None:
    monkeypatch.setattr(csrf, "_SECRET", b"original")

    configure_csrf_secret(secret)

    assert expected == csrf._SECRET


@pytest.mark.parametrize(
    "secret",
    [
        pytest.param("", id="empty-text"),
        pytest.param(b"", id="empty-bytes"),
    ],
)
def test_configure_csrf_secret_rejects_empty_values(secret: str | bytes) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        configure_csrf_secret(secret)


def test_configure_csrf_secret_rejects_other_types() -> None:
    with pytest.raises(TypeError, match="must be str or bytes"):
        configure_csrf_secret(123)


def test_configure_csrf_secret_rejects_short_values() -> None:
    with pytest.raises(ValueError, match="at least 32 bytes"):
        configure_csrf_secret("predictable")


def test_configured_secret_round_trip_and_rotation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(csrf, "_SECRET", b"a" * 32)
    token = csrf.generate_csrf_token()

    assert csrf._check_csrf_token(token) == token

    configure_csrf_secret(b"b" * 32)
    with pytest.raises(ValueError, match="Invalid CSRF token"):
        csrf._check_csrf_token(token)


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param((("Origin", "https://example.test"),), id="origin"),
        pytest.param((("Origin", "https://example.test:443"),), id="explicit-default-port"),
        pytest.param((("Referer", "https://example.test/form?step=2"),), id="referer-fallback"),
    ],
)
def test_check_csrf_origin_accepts_exact_origin(headers: tuple[tuple[str, str], ...]) -> None:
    csrf._check_csrf_origin(_request_with_headers(*headers))


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param((), id="missing-source"),
        pytest.param((("Origin", "null"),), id="null-origin"),
        pytest.param((("Origin", "https://attacker.example"),), id="cross-origin"),
        pytest.param((("Origin", "https://example.test.attacker.example"),), id="hostname-suffix"),
        pytest.param((("Origin", "https://example.test:444"),), id="different-port"),
        pytest.param((("Origin", "https://example.test:0"),), id="explicit-zero-port"),
        pytest.param((("Origin", "https://user@example.test"),), id="userinfo"),
        pytest.param((("Origin", "https://example.test/path"),), id="origin-with-path"),
        pytest.param(
            (("Origin", "https://example.test"), ("Origin", "https://attacker.example")),
            id="multiple-origins",
        ),
        pytest.param((("Referer", "https://attacker.example/form"),), id="cross-origin-referer"),
    ],
)
def test_check_csrf_origin_rejects_nonmatching_source(headers: tuple[tuple[str, str], ...]) -> None:
    with pytest.raises(ValueError, match="source origin"):
        csrf._check_csrf_origin(_request_with_headers(*headers))


@pytest.mark.parametrize("token", [b"not-text", "x" * 257])
def test_check_csrf_token_rejects_invalid_types_and_oversized_values(token: object) -> None:
    with pytest.raises(ValueError, match="Invalid CSRF token"):
        csrf._check_csrf_token(token)


def test_configure_csrf_secret_is_exported_from_air() -> None:
    assert air.configure_csrf_secret is configure_csrf_secret
