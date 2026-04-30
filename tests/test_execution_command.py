import warnings

import pytest
import yaml

import seamless_config
import seamless_config.select as select


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
    monkeypatch.setattr(select, "_current_record", False)
    monkeypatch.setattr(select, "_record_source", None)
    monkeypatch.setattr(select, "_record_command_seen", False)
    monkeypatch.setattr(select, "_current_queue", None)
    monkeypatch.setattr(select, "_queue_source", None)
    monkeypatch.setattr(select, "_queue_cluster", None)
    monkeypatch.setattr(select, "_current_remote", None)
    monkeypatch.setattr(select, "_remote_source", None)
    monkeypatch.setattr(select, "_current_node", None)
    monkeypatch.setattr(select, "_node_source", None)


def _write_clusters_yaml(
    base_dir,
    queues,
    default_queue=None,
    *,
    include_jobserver=False,
    include_daskserver=True,
):
    clusters_dir = base_dir / ".seamless"
    clusters_dir.mkdir(parents=True, exist_ok=True)
    cluster_def = {
        "tunnel": False,
        "frontends": [
            {
                "hostname": "frontend",
            }
        ],
        "type": "local",
        "workers": 1,
    }
    if include_daskserver:
        cluster_def["frontends"][0]["daskserver"] = {
            "network_interface": "lo",
            "port_start": 3100,
            "port_end": 3110,
        }
    if include_jobserver:
        cluster_def["frontends"][0]["jobserver"] = {
            "conda": "test",
            "network_interface": "lo",
            "port_start": 3000,
            "port_end": 3010,
        }
    if queues is not None:
        cluster_def["queues"] = queues
    if default_queue is None and queues:
        default_queue = next(iter(queues))
    cluster_def["default_queue"] = default_queue
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

    try:
        import seamless_config.pure_daskserver
    except Exception:
        return
    monkeypatch.setattr(
        seamless_config.pure_daskserver, "DISABLED", True, raising=False
    )


def _queue_defaults():
    return {
        "conda": "base",
        "walltime": "00:10:00",
        "cores": 1,
        "memory": "1GiB",
        "unknown_task_duration": "1m",
        "target_duration": "5m",
        "maximum_jobs": 1,
    }


def test_execution_defaults_to_process(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        seamless_config.set_workdir(workdir)
        seamless_config.init()

    messages = [str(w.message) for w in caught]
    assert any("falls back to 'process'" in msg for msg in messages)
    assert any("No cluster defined; running without persistence" in msg for msg in messages)
    assert select.get_execution() == "process"


def test_execution_defaults_to_remote_when_cluster_selected(monkeypatch):
    _reset_state(monkeypatch)
    select.select_cluster("demo")
    assert select.get_execution() == "remote"


def test_persistent_defaults_false_without_cluster(monkeypatch):
    _reset_state(monkeypatch)
    assert select.get_persistent() is False


def test_persistent_defaults_true_with_cluster(monkeypatch):
    _reset_state(monkeypatch)
    select.select_cluster("demo")
    assert select.get_persistent() is True


def test_persistent_command_overrides_default(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    workdir = tmp_path / "persistent-command"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    (workdir / "seamless.yaml").write_text(
        "- cluster: demo\n- execution: process\n- persistent: false\n",
        encoding="utf-8",
    )
    seamless_config.set_workdir(workdir)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        seamless_config.init()
    assert select.get_persistent() is False
    messages = [str(w.message) for w in caught]
    assert not any("No cluster defined; running without persistence" in msg for msg in messages)


def test_record_defaults_false(monkeypatch):
    _reset_state(monkeypatch)
    assert select.get_record() is False


def test_record_command_sets_strict_mode(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    workdir = tmp_path / "record-command"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    (workdir / "seamless.yaml").write_text(
        "- execution: process\n- record: true\n",
        encoding="utf-8",
    )
    seamless_config.set_workdir(workdir)
    from seamless_config.config_files import load_config_files

    load_config_files()
    assert select.get_record() is True


def test_select_record_invalidates_record_mode_cache(monkeypatch):
    _reset_state(monkeypatch)
    from seamless_transformer.record_runtime import (
        get_record_mode,
        invalidate_record_mode_cache,
    )

    invalidate_record_mode_cache()
    assert get_record_mode() is False

    select.select_record(True)

    assert get_record_mode() is True


def test_reset_record_before_load_invalidates_record_mode_cache(monkeypatch):
    _reset_state(monkeypatch)
    from seamless_transformer.record_runtime import (
        get_record_mode,
        invalidate_record_mode_cache,
    )

    invalidate_record_mode_cache()
    select.select_record(True, source="command")
    assert get_record_mode() is True

    select.reset_record_before_load()

    assert select.get_record() is False
    assert get_record_mode() is False


def test_explicit_persistent_true_without_cluster_errors(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    workdir = tmp_path / "persistent-without-cluster"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    (workdir / "seamless.yaml").write_text(
        "- execution: process\n- persistent: true\n",
        encoding="utf-8",
    )
    seamless_config.set_workdir(workdir)
    with pytest.raises(seamless_config.ConfigurationError):
        seamless_config.init()


def test_configure_pure_daskserver_uses_queue_in_key(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    workdir = tmp_path / "pure-dask-config"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults()}
    _write_clusters_yaml(tmp_path, queues, default_queue="default")
    seamless_config.set_workdir(workdir)
    from seamless_config.config_files import load_config_files

    load_config_files()
    import seamless_config.tools as tools

    config = tools.configure_pure_daskserver(cluster="demo")
    assert "default" in config["key"]


def test_configure_daskserver_keeps_hostname_for_remote_local_cluster(
    monkeypatch, tmp_path
):
    _reset_state(monkeypatch)
    workdir = tmp_path / "remote-local-cluster"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults()}
    _write_clusters_yaml(tmp_path, queues, default_queue="default")
    clusters_path = tmp_path / ".seamless" / "clusters.yaml"
    cluster_def = yaml.safe_load(clusters_path.read_text(encoding="utf-8"))
    cluster_def["demo"]["tunnel"] = True
    frontend = cluster_def["demo"]["frontends"][0]
    frontend["hostname"] = "remote-frontend"
    frontend["ssh_hostname"] = "remote-login"
    clusters_path.write_text(yaml.safe_dump(cluster_def), encoding="utf-8")
    seamless_config.set_workdir(workdir)
    from seamless_config.config_files import load_config_files

    load_config_files()
    import seamless_config.tools as tools

    config = tools.configure_daskserver(cluster="demo", project="demo")
    assert config["cluster_string"] == "distributed::LocalCluster"
    assert config["hostname"] == "remote-frontend"
    assert config["ssh_hostname"] == "remote-login"
    assert config["tunnel"] is True


def test_configure_daskserver_drops_hostname_for_actual_local_cluster(
    monkeypatch, tmp_path
):
    _reset_state(monkeypatch)
    workdir = tmp_path / "actual-local-cluster"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults()}
    _write_clusters_yaml(tmp_path, queues, default_queue="default")
    clusters_path = tmp_path / ".seamless" / "clusters.yaml"
    cluster_def = yaml.safe_load(clusters_path.read_text(encoding="utf-8"))
    cluster_def["local_cluster"] = "demo"
    cluster_def["demo"]["tunnel"] = True
    frontend = cluster_def["demo"]["frontends"][0]
    frontend["hostname"] = "local-frontend"
    frontend["ssh_hostname"] = "local-login"
    clusters_path.write_text(yaml.safe_dump(cluster_def), encoding="utf-8")
    seamless_config.set_workdir(workdir)
    from seamless_config.config_files import load_config_files

    load_config_files()
    import seamless_config.tools as tools

    config = tools.configure_daskserver(cluster="demo", project="demo")
    assert "hostname" not in config
    assert "ssh_hostname" not in config
    assert "tunnel" not in config


def test_configure_daskserver_injects_selected_node_for_slurm(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    workdir = tmp_path / "node-slurm"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults()}
    _write_clusters_yaml(tmp_path, queues, default_queue="default")
    clusters_path = tmp_path / ".seamless" / "clusters.yaml"
    cluster_def = yaml.safe_load(clusters_path.read_text(encoding="utf-8"))
    cluster_def["demo"]["type"] = "slurm"
    clusters_path.write_text(yaml.safe_dump(cluster_def), encoding="utf-8")
    seamless_config.set_workdir(workdir)
    from seamless_config.config_files import load_config_files

    load_config_files()
    select.select_node("node123")
    import seamless_config.tools as tools

    config = tools.configure_daskserver(cluster="demo", project="demo")
    directives = config["file_parameters"]["job_extra_directives"]
    assert "--nodelist=node123" in directives


def test_remote_execution_requires_cluster(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    workdir = tmp_path / "remote-execution"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    (workdir / "seamless.yaml").write_text(
        "- execution: remote\n- project: demo\n", encoding="utf-8"
    )

    seamless_config.set_workdir(workdir)
    with pytest.raises(seamless_config.ConfigurationError):
        seamless_config.init()


def test_queue_command_selects_existing_queue(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    workdir = tmp_path / "queue-select"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {
        "default": _queue_defaults(),
        "gpu": _queue_defaults()
        | {"conda": "gpu", "cores": 2, "memory": "2GiB", "walltime": "00:20:00"},
    }
    _write_clusters_yaml(tmp_path, queues, default_queue="default", include_jobserver=True)
    (workdir / "seamless.yaml").write_text(
        "- cluster: demo\n- remote: daskserver\n- queue: gpu\n- project: demo\n",
        encoding="utf-8",
    )

    seamless_config.set_workdir(workdir)
    seamless_config.init()

    assert select.get_queue() == "gpu"

    import seamless_config.tools as tools

    config = tools.configure_daskserver()
    assert config["file_parameters"]["walltime"] == "00:20:00"


def test_jobserver_launch_parameters_include_record_mode(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    workdir = tmp_path / "jobserver-record"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults()}
    _write_clusters_yaml(
        tmp_path,
        queues,
        default_queue="default",
        include_jobserver=True,
        include_daskserver=False,
    )
    (workdir / "seamless.yaml").write_text(
        "- cluster: demo\n- execution: remote\n- remote: jobserver\n"
        "- record: true\n- project: demo\n",
        encoding="utf-8",
    )

    seamless_config.set_workdir(workdir)
    seamless_config.init()

    import seamless_config.tools as tools

    config = tools.configure_jobserver()
    assert config["file_parameters"]["record"] is True


def test_daskserver_launch_parameters_include_record_mode(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    workdir = tmp_path / "daskserver-record"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults()}
    _write_clusters_yaml(
        tmp_path,
        queues,
        default_queue="default",
        include_jobserver=False,
        include_daskserver=True,
    )
    (workdir / "seamless.yaml").write_text(
        "- cluster: demo\n- execution: remote\n- remote: daskserver\n"
        "- record: true\n- project: demo\n",
        encoding="utf-8",
    )

    seamless_config.set_workdir(workdir)
    seamless_config.init()

    import seamless_config.tools as tools

    config = tools.configure_daskserver()
    assert config["file_parameters"]["record"] is True


def test_queue_command_requires_known_queue(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    workdir = tmp_path / "queue-missing"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults() | {"walltime": "00:05:00"}}
    _write_clusters_yaml(tmp_path, queues, default_queue="default")
    (workdir / "seamless.yaml").write_text(
        "- cluster: demo\n- queue: missing\n- project: demo\n", encoding="utf-8"
    )

    seamless_config.set_workdir(workdir)
    with pytest.raises(ValueError):
        seamless_config.init()


def test_queue_command_requires_queue_definitions(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    workdir = tmp_path / "queue-empty"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    _write_clusters_yaml(tmp_path, {}, default_queue=None)
    (workdir / "seamless.yaml").write_text(
        "- cluster: demo\n- queue: default\n- project: demo\n", encoding="utf-8"
    )

    seamless_config.set_workdir(workdir)
    with pytest.raises(ValueError):
        seamless_config.init()


def test_remote_command_accepts_allowed_values(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    workdir = tmp_path / "remote-command"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    (workdir / "seamless.yaml").write_text(
        "- remote: jobserver\n- project: demo\n", encoding="utf-8"
    )

    seamless_config.set_workdir(workdir)
    seamless_config.init()

    assert select.get_remote() == "jobserver"


def test_remote_command_rejects_invalid_value(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    workdir = tmp_path / "remote-invalid"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    (workdir / "seamless.yaml").write_text("- remote: worker\n", encoding="utf-8")

    seamless_config.set_workdir(workdir)
    with pytest.raises(ValueError):
        seamless_config.init()


def test_remote_redundancy_requires_remote_setting(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    workdir = tmp_path / "remote-redundancy"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults()}
    _write_clusters_yaml(tmp_path, queues, default_queue="default")
    seamless_yaml = "\n".join(
        [
            "- cluster: demo",
            "- project: demo",
        ]
    )
    (workdir / "seamless.yaml").write_text(seamless_yaml, encoding="utf-8")

    seamless_config.set_workdir(workdir)
    # Patch clusters to contain both jobserver and daskserver on the same frontend
    clusters_path = tmp_path / ".seamless" / "clusters.yaml"
    cluster_def = yaml.safe_load(clusters_path.read_text())
    frontend = cluster_def["demo"]["frontends"][0]
    frontend["jobserver"] = {
        "conda": "test",
        "network_interface": "lo",
        "port_start": 3200,
        "port_end": 3210,
    }
    frontend["daskserver"] = {"network_interface": "lo", "port_start": 3300, "port_end": 3310}
    clusters_path.write_text(yaml.safe_dump(cluster_def), encoding="utf-8")

    with pytest.raises(seamless_config.ConfigurationError):
        seamless_config.init()


def test_remote_redundancy_allowed_when_remote_set(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    workdir = tmp_path / "remote-redundancy-remote"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults()}
    _write_clusters_yaml(tmp_path, queues, default_queue="default")
    seamless_yaml = "\n".join(
        [
            "- cluster: demo",
            "- remote: jobserver",
            "- project: demo",
        ]
    )
    (workdir / "seamless.yaml").write_text(seamless_yaml, encoding="utf-8")

    clusters_path = tmp_path / ".seamless" / "clusters.yaml"
    cluster_def = yaml.safe_load(clusters_path.read_text())
    frontend = cluster_def["demo"]["frontends"][0]
    frontend["jobserver"] = {
        "conda": "test",
        "network_interface": "lo",
        "port_start": 3200,
        "port_end": 3210,
    }
    frontend["daskserver"] = {"network_interface": "lo", "port_start": 3300, "port_end": 3310}
    clusters_path.write_text(yaml.safe_dump(cluster_def), encoding="utf-8")

    seamless_config.set_workdir(workdir)
    seamless_config.init()


def test_remote_redundancy_returns_jobserver(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    workdir = tmp_path / "remote-jobserver-only"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults()}
    _write_clusters_yaml(
        tmp_path, queues, default_queue="default", include_jobserver=True, include_daskserver=False
    )
    seamless_yaml = "\n".join(
        [
            "- cluster: demo",
            "- project: demo",
        ]
    )
    (workdir / "seamless.yaml").write_text(seamless_yaml, encoding="utf-8")

    seamless_config.set_workdir(workdir)
    seamless_config.init()

    assert select.check_remote_redundancy("demo") == "jobserver"


def test_remote_redundancy_returns_daskserver(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    _disable_remote_launch(monkeypatch)
    workdir = tmp_path / "remote-daskserver-only"
    workdir.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path))
    queues = {"default": _queue_defaults()}
    _write_clusters_yaml(
        tmp_path, queues, default_queue="default", include_jobserver=False, include_daskserver=True
    )
    seamless_yaml = "\n".join(
        [
            "- cluster: demo",
            "- project: demo",
        ]
    )
    (workdir / "seamless.yaml").write_text(seamless_yaml, encoding="utf-8")

    seamless_config.set_workdir(workdir)
    seamless_config.init()

    assert select.check_remote_redundancy("demo") == "daskserver"
