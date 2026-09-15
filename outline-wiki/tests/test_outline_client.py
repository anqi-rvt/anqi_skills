from __future__ import annotations

from outline_client import OutlineClient


def test_verify_defaults_to_true(monkeypatch):
    monkeypatch.setenv("OUTLINE_API_KEY", "test-key")
    monkeypatch.delenv("OUTLINE_INSECURE", raising=False)
    assert OutlineClient(base_url="https://example.test").verify is True


def test_verify_false_only_with_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("OUTLINE_API_KEY", "test-key")
    monkeypatch.setenv("OUTLINE_INSECURE", "1")
    assert OutlineClient(base_url="https://example.test").verify is False


def test_verify_explicit_argument_overrides_env(monkeypatch):
    monkeypatch.setenv("OUTLINE_API_KEY", "test-key")
    monkeypatch.setenv("OUTLINE_INSECURE", "1")
    assert OutlineClient(base_url="https://example.test", verify=True).verify is True
