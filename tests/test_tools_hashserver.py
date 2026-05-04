import yaml
import pytest

import seamless_config
import seamless_config.cluster as cluster
import seamless_config.select as select
import seamless_config.tools as tools


def _reset_state(monkeypatch):
    monkeypatch.setattr(seamless_config, "_initialized", False)
    monkeypatch.setattr(seamless_config, "_set_workdir_called", False)
    monkeypatch.setattr(seamless_config, "_remote_clients_set", False)
    monkeypatch.setattr(seamless_config, "_workdir", None)

    monkeypatch.setattr(select, "_current_cluster", None)
    monkeypatch.setattr(select, "_current_project", None)
    monkeypatch.setattr(select, "_current_subproject", None)
    monkeypatch.setattr(select, "_current_stage", None)
    monkeypatch.setattr(select, "_current_substage", None)
    monkeypatch.setattr(select, "_current_execution", "process")
    monkeypatch.setattr(select, "_execution_source", None)
    monkeypatch.setattr(select, "_execution_command_seen", False)
    monkeypatch.setattr(select, "_current_persistent", None)
    monkeypatch.setattr(select, "_persistent_source", None)
    monkeypatch.setattr(select, "_persistent_command_seen", False)
    monkeypatch.setattr(select, "_current_queue", None)
    monkeypatch.setattr(select, "_queue_source", None)
    monkeypatch.setattr(select, "_queue_cluster", None)
    monkeypatch.setattr(select, "_current_remote", None)
    monkeypatch.setattr(select, "_remote_source", None)
    monkeypatch.setattr(cluster, "_local_cluster", None)


def _write_clusters_yaml(base_dir):
    clusters_dir = base_dir / ".seamless"
    clusters_dir.mkdir(parents=True, exist_ok=True)
    cluster_def = {
        "tunnel": False,
        "frontends": [
            {
                "hostname": "frontend",
                "hashserver": {
                    "bufferdir": "/tmp/seamless-hashserver-buffer",
                    "conda": "hashserver",
                    "network_interface": "127.0.0.1",
                    "port_start": 10000,
                    "port_end": 10010,
                },
            }
        ],
        "type": "local",
        "workers": 1,
    }
    (clusters_dir / "clusters.yaml").write_text(
        yaml.safe_dump({"demo": cluster_def}), encoding="utf-8"
    )


def _disable_remote_launch(monkeypatch):
    try:
        import seamless_remote.buffer_remote
        import seamless_remote.database_remote
        import seamless_remote.daskserver_remote
        import seamless_remote.jobserver_remote
    except ImportError:
        return

    monkeypatch.setattr(seamless_remote.buffer_remote, "DISABLED", True, raising=False)
    monkeypatch.setattr(seamless_remote.database_remote, "DISABLED", True, raising=False)
    monkeypatch.setattr(
        seamless_remote.daskserver_remote, "DISABLED", True, raising=False
    )
    monkeypatch.setattr(
        seamless_remote.jobserver_remote, "DISABLED", True, raising=False
    )


@pytest.mark.parametrize("mode,expects_writable", [("ro", False), ("rw", True)])
def test_configure_hashserver_smoke(monkeypatch, tmp_path, mode, expects_writable):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_clusters_yaml(tmp_path)

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    select.select_cluster("demo")
    seamless_config.set_workdir(workdir)
    seamless_config.init()

    config = tools.configure_hashserver(mode=mode, cluster="demo", project="myproject")
    assert isinstance(config, dict)
    for key in (
        "hostname",
        "network_interface",
        "conda",
        "port_start",
        "port_end",
        "timeout",
        "workdir",
        "key",
        "command",
        "handshake",
    ):
        assert key in config

    assert config["hostname"] == "frontend"
    assert config["conda"] == "hashserver"
    assert config["port_start"] == 10000
    assert config["port_end"] == 10010
    assert config["handshake"] == "healthcheck"
    assert f"if '{mode}' == 'rw'" in config["command"]
    assert f"-{mode}-" in config["key"]


def test_cluster_named_local_is_not_special(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    clusters_dir = tmp_path / ".seamless"
    clusters_dir.mkdir(parents=True, exist_ok=True)
    cluster_def = {
        "local_cluster": "actual-local",
        "actual-local": {
            "type": "local",
            "frontends": [{"hashserver": {"bufferdir": "/tmp/actual-local"}}],
        },
        "local": {
            "type": "local",
            "frontends": [
                {
                    "hostname": "remote-frontend",
                    "hashserver": {
                        "bufferdir": "/tmp/local-name-buffer",
                        "conda": "hashserver",
                    },
                }
            ],
        },
    }
    (clusters_dir / "clusters.yaml").write_text(
        yaml.safe_dump(cluster_def), encoding="utf-8"
    )
    seamless_config.set_workdir(workdir)

    seamless_config.init()

    config = tools.configure_hashserver("rw", cluster="local", project="myproject")
    assert config["hostname"] == "remote-frontend"
    assert config["conda"] == "hashserver"


def test_seamless_cache_hashserver_is_actual_local_cluster(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    monkeypatch.setenv("SEAMLESS_CACHE", str(tmp_path / "cache"))

    seamless_config.init()

    config = tools.configure_hashserver("rw")
    assert cluster.get_local_cluster() == "__SEAMLESS_CACHE__"
    assert "hostname" not in config
    assert "ssh_hostname" not in config
    assert "tunnel" not in config
