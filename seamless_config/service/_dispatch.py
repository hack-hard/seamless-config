from __future__ import annotations

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any


@contextmanager
def _temporary_workdir(workdir: str | None):
    if workdir is None:
        yield
        return
    import seamless_config

    old = seamless_config._workdir
    old_called = seamless_config._set_workdir_called
    seamless_config._workdir = os.path.abspath(os.path.expanduser(workdir))
    seamless_config._set_workdir_called = True
    try:
        yield
    finally:
        seamless_config._workdir = old
        seamless_config._set_workdir_called = old_called


def _load_config(*, from_cwd: bool, workdir: str | None = None) -> None:
    import seamless_config.config_files as config_files
    from seamless_config import select

    if from_cwd or workdir is not None:
        with _temporary_workdir(workdir):
            config_files.load_config_files()
        return

    select.reset_execution_before_load()
    select.reset_persistent_before_load()
    select.reset_queue_before_load()
    select.reset_remote_before_load()
    select.reset_record_before_load()
    select.reset_node_before_load()
    config_files.load_tools()
    if not config_files._load_seamless_cache_config():
        clusters = config_files._load_clusters()
        from seamless_config.cluster import define_clusters

        define_clusters(clusters)


def _select_from_args(args) -> None:
    from seamless_config import select

    if getattr(args, "cluster", None) is not None:
        select.select_cluster(args.cluster)
    if getattr(args, "project", None) is not None:
        select.select_project(args.project)
    if getattr(args, "subproject", None) is not None:
        select.select_subproject(args.subproject)
    if getattr(args, "stage", None) is not None:
        select.select_stage(args.stage)
    if getattr(args, "substage", None) is not None:
        select.select_substage(args.substage)
    if getattr(args, "queue", None) is not None:
        try:
            select.select_queue(args.queue)
        except Exception:
            pass


def resolve(args, *, from_cwd=True):
    """Return (key, ssh_hostname, full_config)."""
    _load_config(from_cwd=from_cwd, workdir=getattr(args, "workdir", None))
    _select_from_args(args)

    from seamless_config.tools import (
        configure_database,
        configure_daskserver,
        configure_hashserver,
        configure_jobserver,
        configure_pure_daskserver,
    )

    common = {
        "cluster": args.cluster,
        "frontend_name": getattr(args, "frontend_name", None),
    }
    if args.service == "hashserver":
        config = configure_hashserver(
            args.mode,
            project=args.project,
            subproject=args.subproject,
            stage=args.stage,
            **common,
        )
    elif args.service == "database":
        config = configure_database(
            args.mode,
            project=args.project,
            subproject=args.subproject,
            stage=args.stage,
            **common,
        )
    elif args.service == "jobserver":
        config = configure_jobserver(
            project=args.project,
            subproject=args.subproject,
            stage=args.stage,
            substage=args.substage,
            **common,
        )
    elif args.service == "daskserver":
        config = configure_daskserver(
            project=args.project,
            subproject=args.subproject,
            stage=args.stage,
            substage=args.substage,
            **common,
        )
    elif args.service == "pure-daskserver":
        config = configure_pure_daskserver(
            cluster=args.cluster,
            queue=args.queue,
            frontend_name=getattr(args, "frontend_name", None),
        )
    else:
        raise SystemExit(f"unknown service: {args.service}")

    from remote_http_launcher import Configuration

    launcher_cfg = Configuration.from_mapping(config)
    config = dict(config)
    config["key"] = launcher_cfg.key
    meta = add_meta(config, args)
    config["meta"] = meta
    return config["key"], config.get("ssh_hostname"), config


def add_meta(config, args) -> dict:
    from seamless_config.select import get_current, get_queue

    service = args.service
    try:
        cluster, project, subproject, stage, substage = get_current(
            args.cluster,
            args.project,
            args.subproject,
            args.stage,
            args.substage,
        )
    except Exception:
        cluster = args.cluster
        project = args.project
        subproject = args.subproject
        stage = args.stage
        substage = args.substage
    queue = args.queue or (get_queue(cluster) if cluster else None)
    return {
        "service": service,
        "cluster": cluster,
        "mode": args.mode,
        "project": project,
        "subproject": subproject,
        "stage": stage,
        "substage": substage,
        "queue": queue,
    }


def cluster_ssh_hostname(cluster_name: str, *, frontend_name: str | None = None) -> str | None:
    from seamless_config.cluster import get_cluster, get_local_cluster

    _load_config(from_cwd=True)
    clus = get_cluster(cluster_name)
    frontend = None
    for candidate in clus.frontends:
        if frontend_name is None or candidate.hostname == frontend_name:
            frontend = candidate
            break
    if frontend is None:
        raise SystemExit(f"No frontend for cluster {cluster_name!r}")
    if cluster_name == get_local_cluster():
        return None
    return frontend.ssh_hostname or frontend.hostname


def run_remote(ssh_hostname, *cmd):
    if ssh_hostname:
        return subprocess.run(["ssh", ssh_hostname, *cmd])
    return run_local(*cmd)


def run_remote_capture(ssh_hostname, *cmd) -> str:
    if ssh_hostname:
        result = subprocess.run(["ssh", ssh_hostname, *cmd], text=True, capture_output=True)
    else:
        result = subprocess.run(list(cmd), text=True, capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def run_local(*cmd):
    return subprocess.run(list(cmd))


def run_local_capture(*cmd) -> str:
    result = subprocess.run(list(cmd), text=True, capture_output=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def iter_ndjson(text: str):
    for line in text.splitlines():
        if line.strip():
            yield json.loads(line)


def row_matches_cluster(row: dict[str, Any], cluster: str) -> bool:
    meta = row.get("meta")
    if isinstance(meta, dict) and meta.get("cluster") == cluster:
        return True
    key = str(row.get("key", ""))
    prefixes = [
        f"hashserver-{cluster}-rw-",
        f"hashserver-{cluster}-ro-",
        f"database-{cluster}-rw-",
        f"database-{cluster}-ro-",
        f"jobserver-{cluster}-rw-",
        f"daskserver-{cluster}-rw-",
        f"pure-daskserver-{cluster}-",
    ]
    return any(key.startswith(prefix) for prefix in prefixes)


def row_matches_filters(row: dict[str, Any], args) -> bool:
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    for name in ("service", "cluster", "project", "stage"):
        value = getattr(args, name, None)
        if value is not None and meta.get(name) != value:
            return False
    return True


def remote_log_path(key: str) -> str:
    return f"~/.remote-http-launcher/server/{key}.log"
