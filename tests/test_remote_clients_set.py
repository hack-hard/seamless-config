import json

import pytest

import seamless_config
from seamless_config.extern_clients import set_remote_clients


def test_set_remote_clients_registers_clients(monkeypatch, tmp_path):
    clients = {
        "database": [{"readonly": False, "url": "http://db"}],
        "buffer": [
            {"readonly": True, "directory": "/buffers"},
            {"readonly": False, "url": "http://hash"},
        ],
    }
    path = tmp_path / "clients.json"
    path.write_text(json.dumps(clients), encoding="utf-8")
    loaded = json.loads(path.read_text(encoding="utf-8"))

    db_calls = []
    buf_calls = []

    from seamless_remote import database_remote, buffer_remote

    def db_define(name, type_, **kwargs):
        db_calls.append((name, type_, kwargs))

    def buf_define(name, type_, **kwargs):
        buf_calls.append((name, type_, kwargs))

    monkeypatch.setattr(database_remote, "define_extern_client", db_define)
    monkeypatch.setattr(buffer_remote, "define_extern_client", buf_define)
    monkeypatch.setattr(database_remote, "DISABLED", True)
    monkeypatch.setattr(buffer_remote, "DISABLED", True)
    monkeypatch.setattr(seamless_config, "_initialized", False)
    monkeypatch.setattr(seamless_config, "_remote_clients_set", False)

    set_remote_clients(loaded)

    assert db_calls == [("extern-db-0", "database", {"url": "http://db", "readonly": False})]
    assert buf_calls == [
        ("extern-buffer-0", "bufferfolder", {"directory": "/buffers", "readonly": True}),
        ("extern-buffer-1", "hashserver", {"url": "http://hash", "readonly": False}),
    ]

    with pytest.raises(RuntimeError):
        seamless_config.set_stage()
    with pytest.raises(RuntimeError):
        seamless_config.set_workdir("/tmp")


def test_set_remote_clients_remote_prefers_folder_reads_and_keeps_hashserver_writes(
    monkeypatch,
):
    clients = {
        "database": [
            {
                "readonly": False,
                "url": "http://localhost:1",
                "remote_url": "http://db-remote",
            }
        ],
        "buffer": [
            {
                "readonly": False,
                "url": "http://localhost:2",
                "remote_url": "http://hash-remote",
                "remote_directory": "~/buffers",
            }
        ],
    }

    db_calls = []
    buf_calls = []

    from seamless_remote import database_remote, buffer_remote

    monkeypatch.setenv("HOME", "/home/remote-user")
    monkeypatch.setattr(
        database_remote,
        "define_extern_client",
        lambda *args, **kwargs: db_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        buffer_remote,
        "define_extern_client",
        lambda *args, **kwargs: buf_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(database_remote, "DISABLED", True)
    monkeypatch.setattr(buffer_remote, "DISABLED", True)
    monkeypatch.setattr(seamless_config, "_initialized", False)
    monkeypatch.setattr(seamless_config, "_remote_clients_set", False)

    set_remote_clients(clients, in_remote=True)

    assert db_calls == [
        (("extern-db-0", "database"), {"url": "http://db-remote", "readonly": False})
    ]
    assert buf_calls == [
        (
            ("extern-buffer-0-folder", "bufferfolder"),
            {"directory": "/home/remote-user/buffers", "readonly": True},
        ),
        (
            ("extern-buffer-0-server", "hashserver"),
            {"url": "http://hash-remote", "readonly": False},
        ),
    ]
