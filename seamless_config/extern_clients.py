from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .tools import configure_hashserver


def collect_remote_clients(cluster: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Collect extern and launched database/buffer clients for a given cluster.

    Returns two lists with entries that can be passed to define_extern_client,
    under the keys "database" and "buffer".
    """
    from seamless_remote import buffer_remote, database_remote

    database_entries: list[dict[str, Any]] = []
    buffer_entries: list[dict[str, Any]] = []

    def copy_entry(info: dict[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {"readonly": info["readonly"]}
        if info.get("directory") is not None:
            entry["directory"] = info["directory"]
        if info.get("url") is not None:
            entry["url"] = info["url"]
        if info.get("remote_url") is not None:
            entry["remote_url"] = info["remote_url"]
        if info.get("remote_directory") is not None:
            entry["remote_directory"] = info["remote_directory"]
        return entry

    for info in database_remote.inspect_extern_clients():
        database_entries.append(copy_entry(info))

    for info in database_remote.inspect_launched_clients():
        if info.get("cluster") != cluster:
            continue
        database_entries.append(copy_entry(info))

    for info in buffer_remote.inspect_extern_clients():
        buffer_entries.append(copy_entry(info))

    for info in buffer_remote.inspect_launched_clients():
        if info.get("cluster") != cluster:
            continue
        buffer_entries.append(copy_entry(info))

    return {"database": database_entries, "buffer": buffer_entries}


def set_remote_clients(
    clients: Dict[str, List[Dict[str, Any]]], in_remote=False
) -> None:
    """
    Configure extern buffer/database clients from a collected definition.
    If in_remote, we consider that we are in the remote environment, i.e. locally inside the cluster
    """
    from seamless_remote import buffer_remote, database_remote
    import seamless_config as _config

    if _config._initialized:
        raise RuntimeError("Cannot set remote clients after initialization")
    _config._remote_clients_set = True

    database = clients.get("database", [])
    database_names = []
    buffer = clients.get("buffer", [])
    buffer_names = []

    for idx, entry in enumerate(database):
        readonly = entry.get("readonly", True)
        if in_remote:
            url = entry.get("remote_url")
        else:
            url = entry.get("url")
        if url is None:
            raise ValueError("Database client entry requires 'url'")
        name = f"extern-db-{idx}"
        database_remote.define_extern_client(
            name, "database", url=url, readonly=readonly
        )
        database_names.append(name)

    database_remote.activate(no_main=True, extern_clients=database_names)

    buffer_names = []
    for idx, entry in enumerate(buffer):
        readonly = entry.get("readonly", True)
        if in_remote:
            url = entry.get("remote_url")
            directory = entry.get("remote_directory")
            if directory is not None:
                directory = os.path.expanduser(directory)
        else:
            url = entry.get("url")
            directory = entry.get("directory")
        if directory is not None:
            name = f"extern-buffer-{idx}-folder" if url is not None else f"extern-buffer-{idx}"
            buffer_remote.define_extern_client(
                name, "bufferfolder", directory=directory, readonly=True
            )
            buffer_names.append(name)
        if url is not None:
            name = f"extern-buffer-{idx}-server" if directory is not None else f"extern-buffer-{idx}"
            buffer_remote.define_extern_client(
                name, "hashserver", url=url, readonly=readonly
            )
            buffer_names.append(name)
        if directory is None and url is None:
            raise ValueError("Buffer client entry requires 'url' or 'directory'")

    buffer_remote.activate(no_main=True, extern_clients=buffer_names)


def set_remote_clients_from_env(include_dask: bool) -> bool:
    from . import get_seamless_cache

    if get_seamless_cache() is not None:
        return False
    env_remote_clients = os.environ.get("SEAMLESS_REMOTE_CLIENTS")
    if env_remote_clients is None:
        return False
    try:
        remote_clients = json.loads(env_remote_clients)
        set_remote_clients(remote_clients, in_remote=True)
        if include_dask:
            _configure_dask_client_from_env()
    except Exception:
        pass
    return True


def _configure_dask_client_from_env() -> None:
    try:
        from seamless import is_worker

        if is_worker():
            return
    except Exception:
        return
    scheduler_address = os.environ.get("SEAMLESS_DASK_SCHEDULER")
    if not scheduler_address:
        return
    try:
        from seamless_dask.transformer_client import (
            get_seamless_dask_client,
            set_seamless_dask_client,
        )
    except Exception:
        return
    if get_seamless_dask_client() is not None:
        return
    try:
        from distributed import Client as DistributedClient
        from seamless_dask.client import SeamlessDaskClient

        try:
            worker_count = int(os.environ.get("SEAMLESS_DASK_WORKERS", "1") or 1)
        except Exception:
            worker_count = 1
        dask_client = DistributedClient(
            scheduler_address, timeout="10s", set_as_default=False
        )
        sd_client = SeamlessDaskClient(
            dask_client,
            worker_plugin_workers=worker_count,
        )
        set_seamless_dask_client(sd_client)
    except Exception:
        pass
