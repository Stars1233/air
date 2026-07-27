import pytest

import air.form.csrf as csrf


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
