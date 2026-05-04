from seamless_config.service._dispatch import row_matches_filters
from seamless_config.service.ps import _process_row


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
