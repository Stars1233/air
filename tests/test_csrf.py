import pytest

import air
import air.form.csrf as csrf
from air.form import configure_csrf_secret


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
    monkeypatch.setenv("AIRFORM_SECRET", "configured")
    monkeypatch.setattr(csrf.sys, "platform", "emscripten")

    assert csrf._initial_secret() == b"configured"


@pytest.mark.parametrize(
    ("secret", "expected"),
    [
        pytest.param("configured", b"configured", id="text-secret"),
        pytest.param(b"configured", b"configured", id="byte-secret"),
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


def test_configure_csrf_secret_is_exported_from_air() -> None:
    assert air.configure_csrf_secret is configure_csrf_secret
