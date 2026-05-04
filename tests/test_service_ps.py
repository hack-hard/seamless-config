from seamless_config.service._dispatch import row_matches_filters
from seamless_config.service.ps import _process_row
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


def test_service_ps_project_filter_accepts_seamless_cache_alias():
    args = Args()
    args.project = "SEAMLESS_CACHE"
    row = {
        "key": "hashserver-__SEAMLESS_CACHE__-rw-__TOPLEVEL__",
        "meta": {},
    }

    assert row_matches_filters(row, args)


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
