from pathlib import Path

import pytest
import yaml

from seamless_config.config_files import _PLATFORM_DIRS, get_seamless_config_paths


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Give every test a clean HOME with no legacy dir and no env overrides."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("SEAMLESS_CONFIG_DIR", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return home


# --- Path selection ---


def test_env_override_returned(tmp_path, monkeypatch):
    override = tmp_path / "custom"
    monkeypatch.setenv("SEAMLESS_CONFIG_DIR", str(override))
    assert get_seamless_config_paths() == override


def test_env_override_created_if_missing(tmp_path, monkeypatch):
    override = tmp_path / "custom"
    monkeypatch.setenv("SEAMLESS_CONFIG_DIR", str(override))
    get_seamless_config_paths()
    assert override.is_dir()


def test_env_override_beats_legacy(tmp_path, monkeypatch, isolated_home):
    (isolated_home / ".seamless").mkdir(parents=True)
    override = tmp_path / "override"
    monkeypatch.setenv("SEAMLESS_CONFIG_DIR", str(override))
    assert get_seamless_config_paths() == override


def test_legacy_path_used_when_exists(isolated_home):
    legacy = isolated_home / ".seamless"
    legacy.mkdir(parents=True)
    assert get_seamless_config_paths() == legacy


def test_platformdirs_used_when_no_legacy(isolated_home):
    result = get_seamless_config_paths()
    assert result != isolated_home / ".seamless"
    assert result.is_dir()


# --- Default config creation ---


def test_default_config_created_on_new_dir():
    result = get_seamless_config_paths()
    assert (result / "clusters.yaml").exists()


def test_default_config_is_valid_yaml():
    result = get_seamless_config_paths()
    data = yaml.safe_load((result / "clusters.yaml").read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_default_config_has_local_cluster():
    result = get_seamless_config_paths()
    data = yaml.safe_load((result / "clusters.yaml").read_text(encoding="utf-8"))
    assert data.get("local_cluster") == "local"
    assert "local" in data
    assert data["local"]["type"] == "local"


def test_default_config_paths_use_xdg_dirs():
    result = get_seamless_config_paths()
    data = yaml.safe_load((result / "clusters.yaml").read_text(encoding="utf-8"))
    frontend = data["local"]["frontends"][0]
    assert Path(frontend["hashserver"]["bufferdir"]) == Path(_PLATFORM_DIRS.user_cache_dir)
    assert Path(frontend["database"]["database_dir"]) == Path(_PLATFORM_DIRS.user_data_dir)


def test_default_config_xdg_subdirs_created():
    get_seamless_config_paths()
    assert Path(_PLATFORM_DIRS.user_cache_dir).is_dir()
    assert Path(_PLATFORM_DIRS.user_data_dir).is_dir()


def test_default_config_not_created_for_existing_dir():
    result = get_seamless_config_paths()
    clusters_file = result / "clusters.yaml"
    clusters_file.unlink()
    get_seamless_config_paths()
    assert not clusters_file.exists()


def test_default_config_not_overwritten_by_env_override(tmp_path, monkeypatch):
    override = tmp_path / "existing_config"
    override.mkdir()
    custom = "custom: content\n"
    (override / "clusters.yaml").write_text(custom, encoding="utf-8")
    monkeypatch.setenv("SEAMLESS_CONFIG_DIR", str(override))
    get_seamless_config_paths()
    assert (override / "clusters.yaml").read_text(encoding="utf-8") == custom


def test_no_default_config_for_legacy_dir(isolated_home):
    legacy = isolated_home / ".seamless"
    legacy.mkdir(parents=True)
    get_seamless_config_paths()
    assert not (legacy / "clusters.yaml").exists()


def test_env_override_new_dir_gets_default_config(tmp_path, monkeypatch):
    override = tmp_path / "fresh"
    monkeypatch.setenv("SEAMLESS_CONFIG_DIR", str(override))
    result = get_seamless_config_paths()
    assert (result / "clusters.yaml").exists()
