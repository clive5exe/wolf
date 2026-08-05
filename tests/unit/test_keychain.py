"""Keychain wrapper: argv shape, error mapping. Subprocess fully mocked."""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from tradeos.security import keychain


class _Recorder:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.calls: list[list[str]] = []
        self._rc = returncode
        self._stdout = stdout

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append(argv)
        return subprocess.CompletedProcess(argv, self._rc, stdout=self._stdout, stderr="")


def test_set_secret_uses_update_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(subprocess, "run", recorder)
    keychain.set_secret("alpha_vantage", "value-123")
    argv = recorder.calls[0]
    assert argv[0] == "/usr/bin/security" and "add-generic-password" in argv
    assert "-U" in argv
    assert "tradeos.alpha_vantage" in argv


def test_get_secret_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", _Recorder(stdout="s3cret\n"))
    assert keychain.get_secret("alpha_vantage") == "s3cret"


def test_get_secret_missing_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", _Recorder(returncode=44))
    assert keychain.get_secret("nope") is None


def test_set_failure_raises_without_leaking_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", _Recorder(returncode=1))
    with pytest.raises(keychain.KeychainError) as excinfo:
        keychain.set_secret("svc", "super-secret-value")
    assert "super-secret-value" not in str(excinfo.value)


def test_invalid_names_rejected() -> None:
    with pytest.raises(keychain.KeychainError):
        keychain.get_secret("bad/name")
    with pytest.raises(keychain.KeychainError):
        keychain.get_secret("")
