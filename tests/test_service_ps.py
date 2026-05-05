import json

import seamless_config.service.clear as clear
import seamless_config.service.ps as ps
from seamless_config.service._dispatch import normalize_project_arg, resolve, row_matches_filters
from seamless_config.service.ps import _merge_rows, _persistent_row, _process_row
from seamless_config.service.stop import _mark_client_stale


class Args:
    service = None
    cluster = None
    project = None
    stage = None


def test_service_ps_displays_seamless_cache_toplevel_project():
    row = {
        "key": "hashserver-__SEAMLESS_CACHE__-rw-__TOPLEVEL__",
        "port": 1234,
        "meta": {},
    }

    rendered = _process_row(row)

    assert rendered["service"] == "hashserver"
    assert rendered["cluster"] == "__SEAMLESS_CACHE__"
    assert rendered["project"] == "SEAMLESS_CACHE"


def test_service_ps_persistent_row_preserves_project_for_stage_path():
    rendered = _persistent_row(
        {
            "path": "/tmp/seamless-buffers/myproject/STAGE-fingertip",
            "state": "populated",
            "size": None,
        },
        "hashserver",
        "local",
        root="/tmp/seamless-buffers",
    )

    assert rendered["project"] == "myproject"
    assert rendered["stage"] == "fingertip"
    assert rendered["persistent"] == "populated"


def test_service_ps_cluster_view_probes_persistent_cluster_roots(monkeypatch, capsys):
    calls = []

    def fake_run_remote_capture(ssh_host, *cmd):
        calls.append((ssh_host, cmd))
        if cmd[0] == "rhl-ps":
            return ""
        if cmd[0] == "rhl-ps-persistent" and cmd[-1] == "/tmp/seamless-buffers":
            return json.dumps({"path": "/tmp/seamless-buffers/myproject", "state": "populated", "size": None}) + "\n"
        if cmd[0] == "rhl-ps-persistent" and cmd[-1] == "/tmp/seamless-db":
            return json.dumps({"path": "/tmp/seamless-db/myproject", "state": "populated", "size": 7}) + "\n"
        raise AssertionError(cmd)

    monkeypatch.setattr(ps, "cluster_ssh_hostname", lambda cluster, frontend_name=None: None)
    monkeypatch.setattr(
        ps,
        "_persistent_specs_for_cluster",
        lambda args, cluster: [
            ("hashserver", cluster, None, "/tmp/seamless-buffers", None, ".HASHSERVER_PREFIX"),
            ("database", cluster, None, "/tmp/seamless-db", "seamless.db", "seamless.db"),
        ],
    )
    monkeypatch.setattr(ps, "run_remote_capture", fake_run_remote_capture)

    assert ps.main(["--cluster", "local", "--json"]) == 0

    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert {row["service"] for row in rows} == {"hashserver", "database"}
    assert all(row["project"] == "myproject" for row in rows)
    assert (None, ("rhl-ps", "--json")) in calls
    assert (
        None,
        (
            "rhl-ps-persistent",
            "--json",
            "--level",
            "2",
            "--marker",
            ".HASHSERVER_PREFIX",
            "/tmp/seamless-buffers",
        ),
    ) in calls
    assert (
        None,
        (
            "rhl-ps-persistent",
            "--json",
            "--level",
            "2",
            "--file",
            "seamless.db",
            "--marker",
            "seamless.db",
            "/tmp/seamless-db",
        ),
    ) in calls


def test_service_ps_merges_process_and_persistent_rows():
    rows = [
        {
            "service": "hashserver",
            "cluster": "local",
            "project": "seamless-test",
            "stage": None,
            "process": "running",
            "port": 10497,
            "persistent": None,
            "size": None,
            "key": "hashserver-local-rw-seamless-test",
        }
    ]

    _merge_rows(
        rows,
        [
            {
                "service": "hashserver",
                "cluster": "local",
                "project": "seamless-test",
                "stage": None,
                "process": None,
                "port": None,
                "persistent": "populated",
                "size": None,
                "key": None,
                "path": "/tmp/seamless-buffers/seamless-test",
            }
        ],
    )

    assert len(rows) == 1
    assert rows[0]["process"] == "running"
    assert rows[0]["port"] == 10497
    assert rows[0]["persistent"] == "populated"
    assert rows[0]["path"] == "/tmp/seamless-buffers/seamless-test"


def test_service_ps_project_filter_accepts_seamless_cache_alias():
    args = Args()
    args.project = "SEAMLESS_CACHE"
    row = {
        "key": "hashserver-__SEAMLESS_CACHE__-rw-__TOPLEVEL__",
        "meta": {},
    }

    assert row_matches_filters(row, args)


def test_service_helpers_translate_seamless_cache_project_alias(monkeypatch, tmp_path):
    import seamless_config
    import seamless_config.cluster as cluster
    import seamless_config.select as select

    monkeypatch.setenv("SEAMLESS_CACHE", (tmp_path / "cache").as_posix())
    monkeypatch.setattr(seamless_config, "_workdir", None)
    monkeypatch.setattr(seamless_config, "_set_workdir_called", False)
    monkeypatch.setattr(select, "_current_cluster", None)
    monkeypatch.setattr(select, "_current_project", None)
    monkeypatch.setattr(select, "_current_subproject", None)
    monkeypatch.setattr(select, "_current_stage", None)
    monkeypatch.setattr(select, "_current_substage", None)
    monkeypatch.setattr(select, "_current_queue", None)
    monkeypatch.setattr(select, "_queue_cluster", None)
    monkeypatch.setattr(cluster, "_local_cluster", None)
    cluster._clusters.clear()

    args = Args()
    args.service = "hashserver"
    args.cluster = None
    args.project = "SEAMLESS_CACHE"
    args.subproject = None
    args.stage = None
    args.substage = None
    args.mode = "rw"
    args.queue = None
    args.frontend_name = None

    key, ssh_host, config = resolve(args, from_cwd=False)

    assert normalize_project_arg("SEAMLESS_CACHE") == "__TOPLEVEL__"
    assert key == "hashserver-__SEAMLESS_CACHE__-rw-__TOPLEVEL__"
    assert ssh_host is None
    assert config["meta"]["cluster"] == "__SEAMLESS_CACHE__"
    assert config["meta"]["project"] == "__TOPLEVEL__"
    assert config["workdir"].endswith("/__TOPLEVEL__")


def test_service_helpers_read_seamless_cache_workdir_from_json(monkeypatch, tmp_path):
    import seamless_config
    import seamless_config.cluster as cluster
    import seamless_config.select as select

    state_dir = tmp_path / "rhl" / "server"
    state_dir.mkdir(parents=True)
    json_workdir = tmp_path / "json-cache" / "__TOPLEVEL__"
    state = state_dir / "hashserver-__SEAMLESS_CACHE__-rw-__TOPLEVEL__.json"
    state.write_text(json.dumps({"workdir": json_workdir.as_posix()}), encoding="utf-8")
    monkeypatch.setenv("REMOTE_HTTP_LAUNCHER_DIR", (tmp_path / "rhl").as_posix())
    monkeypatch.setenv("SEAMLESS_CACHE", (tmp_path / "env-cache").as_posix())
    monkeypatch.setattr(seamless_config, "_workdir", None)
    monkeypatch.setattr(seamless_config, "_set_workdir_called", False)
    monkeypatch.setattr(select, "_current_cluster", None)
    monkeypatch.setattr(select, "_current_project", None)
    monkeypatch.setattr(select, "_current_subproject", None)
    monkeypatch.setattr(select, "_current_stage", None)
    monkeypatch.setattr(select, "_current_substage", None)
    monkeypatch.setattr(select, "_current_queue", None)
    monkeypatch.setattr(select, "_queue_cluster", None)
    monkeypatch.setattr(cluster, "_local_cluster", None)
    cluster._clusters.clear()

    args = Args()
    args.service = "hashserver"
    args.cluster = None
    args.project = "SEAMLESS_CACHE"
    args.subproject = None
    args.stage = None
    args.substage = None
    args.mode = "rw"
    args.queue = None
    args.frontend_name = None

    _key, _ssh_host, config = resolve(args, from_cwd=False)

    assert config["workdir"] == json_workdir.as_posix()


def test_service_helpers_read_seamless_cache_workdir_from_hashserver_json(monkeypatch, tmp_path):
    import seamless_config
    import seamless_config.cluster as cluster
    import seamless_config.select as select

    state_dir = tmp_path / "rhl" / "server"
    state_dir.mkdir(parents=True)
    json_workdir = tmp_path / "json-cache" / "__TOPLEVEL__"
    state = state_dir / "hashserver-__SEAMLESS_CACHE__-rw-__TOPLEVEL__.json"
    state.write_text(json.dumps({"workdir": json_workdir.as_posix()}), encoding="utf-8")
    monkeypatch.setenv("REMOTE_HTTP_LAUNCHER_DIR", (tmp_path / "rhl").as_posix())
    monkeypatch.delenv("SEAMLESS_CACHE", raising=False)
    monkeypatch.setattr(seamless_config, "_workdir", None)
    monkeypatch.setattr(seamless_config, "_set_workdir_called", False)
    monkeypatch.setattr(select, "_current_cluster", None)
    monkeypatch.setattr(select, "_current_project", None)
    monkeypatch.setattr(select, "_current_subproject", None)
    monkeypatch.setattr(select, "_current_stage", None)
    monkeypatch.setattr(select, "_current_substage", None)
    monkeypatch.setattr(select, "_current_queue", None)
    monkeypatch.setattr(select, "_queue_cluster", None)
    monkeypatch.setattr(cluster, "_local_cluster", None)
    cluster._clusters.clear()

    args = Args()
    args.service = "database"
    args.cluster = None
    args.project = "SEAMLESS_CACHE"
    args.subproject = None
    args.stage = None
    args.substage = None
    args.mode = "rw"
    args.queue = None
    args.frontend_name = None

    _key, _ssh_host, config = resolve(args, from_cwd=False)

    assert config["workdir"] == json_workdir.as_posix()


def test_service_helpers_seamless_cache_requires_json_or_env(monkeypatch, tmp_path):
    import seamless_config
    import seamless_config.cluster as cluster
    import seamless_config.select as select

    monkeypatch.setenv("REMOTE_HTTP_LAUNCHER_DIR", (tmp_path / "rhl").as_posix())
    monkeypatch.delenv("SEAMLESS_CACHE", raising=False)
    monkeypatch.setattr(seamless_config, "_workdir", None)
    monkeypatch.setattr(seamless_config, "_set_workdir_called", False)
    monkeypatch.setattr(select, "_current_cluster", None)
    monkeypatch.setattr(select, "_current_project", None)
    monkeypatch.setattr(select, "_current_subproject", None)
    monkeypatch.setattr(select, "_current_stage", None)
    monkeypatch.setattr(select, "_current_substage", None)
    monkeypatch.setattr(select, "_current_queue", None)
    monkeypatch.setattr(select, "_queue_cluster", None)
    monkeypatch.setattr(cluster, "_local_cluster", None)
    cluster._clusters.clear()

    args = Args()
    args.service = "hashserver"
    args.cluster = None
    args.project = "SEAMLESS_CACHE"
    args.subproject = None
    args.stage = None
    args.substage = None
    args.mode = "rw"
    args.queue = None
    args.frontend_name = None

    try:
        resolve(args, from_cwd=False)
    except SystemExit as exc:
        assert "requires an existing launcher JSON" in str(exc)
    else:
        raise AssertionError("resolve should fail without JSON workdir or SEAMLESS_CACHE")


def test_service_stop_marks_client_state_stale(monkeypatch, tmp_path):
    client_dir = tmp_path / "client"
    client_dir.mkdir()
    state = client_dir / "hashserver-demo-rw-project.json"
    state.write_text('{"hostname": "localhost", "port": 1234}', encoding="utf-8")
    monkeypatch.setenv("REMOTE_HTTP_LAUNCHER_DIR", str(tmp_path))

    _mark_client_stale(["hashserver-demo-rw-project"])
    rendered = _process_row(
        {
            "key": "hashserver-demo-rw-project",
            "hostname": "localhost",
            "port": 1234,
            "status": "stale",
            "meta": {},
        }
    )

    assert '"status": "stale"' in state.read_text(encoding="utf-8")
    assert rendered["process"] == "stale"


def test_service_clear_expands_local_workdir(monkeypatch, tmp_path):
    calls = []

    class Args:
        service = "database"

    class Parser:
        def parse_args(self, argv):
            return Args()

        def error(self, message):
            raise AssertionError(message)

    class Result:
        returncode = 0

    def fake_run_remote(ssh_host, *cmd):
        calls.append((ssh_host, cmd))
        return Result()

    monkeypatch.setattr(clear, "make_parser", lambda *args, **kwargs: Parser())
    monkeypatch.setattr(
        clear,
        "resolve",
        lambda args, from_cwd=True: ("database-local-rw-BLAH", None, {"workdir": "~/seamless-buffers/BLAH"}),
    )
    monkeypatch.setattr(clear, "run_remote", fake_run_remote)
    monkeypatch.setenv("HOME", tmp_path.as_posix())

    assert clear.main([]) == 0
    assert calls == [(None, ("rhl-clear", (tmp_path / "seamless-buffers/BLAH").as_posix()))]
