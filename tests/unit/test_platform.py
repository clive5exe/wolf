"""Cross-platform paths, secret storage, and notifier selection.

The property that matters most here is negative: when no OS credential store
exists, WOLF must refuse rather than quietly fall back to a file. A silent
downgrade would turn a protected machine into an unprotected one with nothing
on screen to say so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tradeos import platform_paths
from tradeos.notifications.base import NullNotifier
from tradeos.notifications.factory import default_notifier, notifier_status
from tradeos.security.store import (
    NoSecureStore,
    SecretStoreError,
    UnavailableStore,
    default_secret_store,
    validate_name,
)


class TestDataDir:
    def test_env_override_wins(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("WOLF_DATA_DIR", str(tmp_path / "custom"))
        assert platform_paths.default_data_dir() == tmp_path / "custom"

    def test_legacy_env_var_still_honoured(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("WOLF_DATA_DIR", raising=False)
        monkeypatch.setenv("TRADEOS_DATA_DIR", str(tmp_path / "legacy"))
        assert platform_paths.default_data_dir() == tmp_path / "legacy"

    @pytest.mark.parametrize(
        ("plat", "expected_fragment"),
        [
            ("darwin", "Application Support"),
            ("linux", ".local/share/wolf"),
            ("win32", "WOLF"),
        ],
    )
    def test_each_platform_uses_its_own_convention(
        self,
        monkeypatch: pytest.MonkeyPatch,
        plat: str,
        expected_fragment: str,
    ) -> None:
        monkeypatch.delenv("WOLF_DATA_DIR", raising=False)
        monkeypatch.delenv("TRADEOS_DATA_DIR", raising=False)
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        monkeypatch.setattr(platform_paths.sys, "platform", plat)
        monkeypatch.setattr(platform_paths, "legacy_data_dir", lambda: None)
        assert expected_fragment in platform_paths.default_data_dir().as_posix()

    def test_xdg_data_home_is_respected_on_linux(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("WOLF_DATA_DIR", raising=False)
        monkeypatch.delenv("TRADEOS_DATA_DIR", raising=False)
        monkeypatch.setattr(platform_paths.sys, "platform", "linux")
        monkeypatch.setattr(platform_paths, "legacy_data_dir", lambda: None)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        assert platform_paths.default_data_dir() == tmp_path / "xdg" / "wolf"

    def test_an_existing_pre_rename_directory_is_adopted_in_place(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """The event log is the audit source of truth. A rename that pointed a
        working install at an empty database would destroy history silently."""
        monkeypatch.delenv("WOLF_DATA_DIR", raising=False)
        monkeypatch.delenv("TRADEOS_DATA_DIR", raising=False)
        legacy = tmp_path / "TradeOS"
        legacy.mkdir()
        (legacy / platform_paths.DB_FILENAME).write_text("")
        monkeypatch.setattr(platform_paths, "_LEGACY_MAC_DIR", legacy)
        assert platform_paths.default_data_dir() == legacy

    def test_database_filename_is_not_renamed_with_the_product(self) -> None:
        assert platform_paths.DB_FILENAME == "tradeos.db"


class TestSecretStore:
    def test_names_are_validated_and_namespaced(self) -> None:
        # Prefix intentionally still "tradeos.". It addresses existing keystore items.
        assert validate_name("robinhood") == "tradeos.robinhood"
        for bad in ("", "has space", "has/slash"):
            with pytest.raises(SecretStoreError):
                validate_name(bad)

    def test_no_store_refuses_every_operation(self) -> None:
        """The critical negative: never a silent fallback to disk."""
        store = UnavailableStore("no keystore here")
        assert not store.available()
        with pytest.raises(NoSecureStore):
            store.set_secret("robinhood", "hunter2")
        with pytest.raises(NoSecureStore):
            store.get_secret("robinhood")
        with pytest.raises(NoSecureStore):
            store.delete_secret("robinhood")

    def test_refusal_explains_how_to_fix_it(self) -> None:
        store = UnavailableStore("`secret-tool` was not found on PATH")
        with pytest.raises(NoSecureStore, match="libsecret"):
            store.set_secret("x", "y")

    def test_windows_reports_unimplemented_rather_than_pretending(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import tradeos.security.store as store_mod

        monkeypatch.setattr(store_mod.sys, "platform", "win32")
        store = default_secret_store()
        assert not store.available()
        assert "Windows" in getattr(store, "reason", "")

    def test_this_machine_resolves_to_something(self) -> None:
        store = default_secret_store()
        assert store.name


class TestNotifier:
    def test_missing_notifier_degrades_to_silence_not_an_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Opposite of the secrets rule, deliberately: a lost banner costs
        awareness, a lost keystore would cost credentials."""
        import tradeos.notifications.factory as factory

        monkeypatch.setattr(factory.sys, "platform", "sunos5")
        assert isinstance(default_notifier(), NullNotifier)

    def test_status_always_explains_itself(self) -> None:
        available, detail = notifier_status()
        assert isinstance(available, bool)
        assert detail
