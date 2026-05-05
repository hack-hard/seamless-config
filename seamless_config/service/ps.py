from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import copy
from pathlib import PurePosixPath

from ._args import make_parser
from ._dispatch import (
    _load_config,
    cluster_ssh_hostname,
    iter_ndjson,
    row_matches_filters,
    row_meta,
    run_local_capture,
    run_remote_capture,
    resolve,
)

SEAMLESS_CACHE_CLUSTER = "__SEAMLESS_CACHE__"
PROJECT_TOPLEVEL = "__TOPLEVEL__"


def _emit_json(rows):
    for row in rows:
        print(json.dumps(row, sort_keys=True))


def _table(rows):
    headers = ("SERVICE", "PROJECT", "STAGE", "PROCESS", "PORT", "PERSISTENT", "SIZE")
    rendered = []
    for row in rows:
        rendered.append([
            row.get("service") or "-",
            row.get("project") or "-",
            row.get("stage") or "-",
            row.get("process") or "-",
            row.get("port") or "-",
            row.get("persistent") or "-",
            row.get("size") if row.get("size") is not None else "-",
        ])
    widths = [len(h) for h in headers]
    for row in rendered:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    print(" ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    for row in rendered:
        print(" ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))


def _process_row(row):
    meta = row_meta(row)
    return {
        "service": meta.get("service"),
        "cluster": meta.get("cluster"),
        "project": _display_project(meta.get("project"), meta.get("cluster")),
        "stage": meta.get("stage"),
        "process": row.get("status") or ("client" if row.get("port") is not None else None),
        "port": row.get("port"),
        "persistent": None,
        "size": None,
        "key": row.get("key"),
    }


def _display_project(project, cluster):
    if project == PROJECT_TOPLEVEL and cluster == SEAMLESS_CACHE_CLUSTER:
        return "SEAMLESS_CACHE"
    return project


def _persistent_path_parts(path, root):
    if not path:
        return []
    path_obj = PurePosixPath(path)
    if root:
        root_obj = PurePosixPath(root)
        try:
            return list(path_obj.relative_to(root_obj).parts)
        except ValueError:
            root_parts = root_obj.parts
            if root_parts and root_parts[0] == "~":
                root_parts = root_parts[1:]
            path_parts = path_obj.parts
            for index in range(len(path_parts) - len(root_parts) + 1):
                if path_parts[index:index + len(root_parts)] == root_parts:
                    return list(path_parts[index + len(root_parts):])
    name = path.rstrip("/").split("/")[-1]
    return [name] if name else []


def _persistent_row(row, service, cluster, *, root=None):
    parts = _persistent_path_parts(row.get("path", ""), root)
    stage = None
    project_parts = parts
    for index, part in enumerate(parts):
        if part.startswith("STAGE-"):
            stage = part.removeprefix("STAGE-")
            project_parts = parts[:index]
            break
    project = "/".join(project_parts) or None
    project = _display_project(project, cluster)
    return {
        "service": service,
        "cluster": cluster,
        "project": project,
        "stage": stage,
        "process": None,
        "port": None,
        "persistent": row.get("state"),
        "size": row.get("size"),
        "key": None,
        "path": row.get("path"),
    }


def _persistent_row_matches_filters(row, args):
    for name in ("service", "cluster", "project", "stage"):
        value = getattr(args, name, None)
        actual = row.get(name)
        if value is not None and actual != value:
            return False
    return True


def _row_identity(row):
    return (row.get("service"), row.get("cluster"), row.get("project"), row.get("stage"))


def _merge_row(rows, row):
    identity = _row_identity(row)
    for existing in rows:
        if _row_identity(existing) != identity:
            continue
        if existing.get("process") is None and row.get("process") is not None:
            existing["process"] = row.get("process")
            existing["port"] = row.get("port")
            existing["key"] = row.get("key")
        if existing.get("persistent") is None and row.get("persistent") is not None:
            existing["persistent"] = row.get("persistent")
            existing["size"] = row.get("size")
            existing["path"] = row.get("path")
        return
    rows.append(row)


def _merge_rows(rows, new_rows):
    for row in new_rows:
        _merge_row(rows, row)


def _known_clusters():
    from seamless_config.config_files import load_config_files
    from seamless_config.cluster import _clusters

    load_config_files()
    return list(_clusters)


def _cluster_frontend(cluster_name, *, frontend_name=None):
    from seamless_config.cluster import get_cluster, get_local_cluster

    _load_config(from_cwd=True)
    clus = get_cluster(cluster_name)
    for frontend in clus.frontends:
        if frontend_name is None or frontend.hostname == frontend_name:
            ssh_host = None
            if cluster_name != get_local_cluster():
                ssh_host = frontend.ssh_hostname or frontend.hostname
            return clus, frontend, ssh_host
    raise SystemExit(f"No frontend for cluster {cluster_name!r}")


def _persistent_specs_for_cluster(args, cluster):
    clus, frontend, ssh_host = _cluster_frontend(cluster, frontend_name=args.frontend_name)
    requested_service = args.service
    specs = []
    if (
        (requested_service is None or requested_service == "hashserver")
        and frontend.hashserver is not None
    ):
        root = os.path.expanduser(frontend.hashserver.bufferdir) if ssh_host is None else frontend.hashserver.bufferdir
        specs.append(("hashserver", clus.name, ssh_host, root, None, ".HASHSERVER_PREFIX"))
    if (
        (requested_service is None or requested_service == "database")
        and frontend.database is not None
    ):
        root = os.path.expanduser(frontend.database.database_dir) if ssh_host is None else frontend.database.database_dir
        specs.append(
            ("database", clus.name, ssh_host, root, "seamless.db", "seamless.db")
        )
    return specs


def _persistent_specs_from_resolve(args):
    requested_service = args.service
    specs = []
    for service in ("hashserver", "database"):
        if requested_service and requested_service != service:
            continue
        probe_args = copy(args)
        probe_args.service = service
        try:
            _key, ssh_host, config = resolve(probe_args, from_cwd=True)
        except Exception as exc:
            print(f"seamless-service-ps: persistent {service}: {exc}", file=sys.stderr)
            continue
        filename = "seamless.db" if service == "database" else None
        marker = "seamless.db" if service == "database" else ".HASHSERVER_PREFIX"
        specs.append(
            (service, config.get("meta", {}).get("cluster"), ssh_host, config["workdir"], filename, marker)
        )
    return specs


def _persistent_specs(args, *, cluster_view):
    if args.all_clusters:
        specs = []
        for cluster in _known_clusters():
            try:
                specs.extend(_persistent_specs_for_cluster(args, cluster))
            except Exception as exc:
                print(f"seamless-service-ps: persistent {cluster}: {exc}", file=sys.stderr)
        return specs
    if args.cluster:
        return _persistent_specs_for_cluster(args, args.cluster)
    if cluster_view:
        return []
    return _persistent_specs_from_resolve(args)


def main(argv=None) -> int:
    parser = make_parser("seamless-service-ps", "List Seamless services.")
    side = parser.add_mutually_exclusive_group()
    side.add_argument("--client", action="store_true")
    side.add_argument("--server", action="store_true")
    side.add_argument("--all-clusters", action="store_true")
    parser.add_argument("--status")
    parser.add_argument("--persistent", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    rows = []
    cluster_view = bool(args.cluster and not args.client and not args.server and not args.all_clusters)
    if args.server or cluster_view:
        if not args.cluster:
            parser.error("--server requires --cluster")
        ssh_host = cluster_ssh_hostname(args.cluster, frontend_name=args.frontend_name)
        cmd = ["rhl-ps", "--json"]
        if args.status:
            cmd.extend(["--status", args.status])
        process_rows = list(iter_ndjson(run_remote_capture(ssh_host, *cmd)))
    elif args.all_clusters:
        process_rows = []
        for cluster in _known_clusters():
            try:
                ssh_host = cluster_ssh_hostname(cluster, frontend_name=args.frontend_name)
                process_rows.extend(iter_ndjson(run_remote_capture(ssh_host, "rhl-ps", "--json")))
            except Exception as exc:
                print(f"seamless-service-ps: {cluster}: {exc}", file=sys.stderr)
    else:
        cmd = ["rhl-ps", "--client", "--json"]
        if args.status:
            cmd.extend(["--status", args.status])
        process_rows = list(iter_ndjson(run_local_capture(*cmd)))

    _merge_rows(rows, (_process_row(row) for row in process_rows if row_matches_filters(row, args)))

    include_persistent = args.persistent or (cluster_view and not args.status)
    if include_persistent:
        for service, cluster, ssh_host, root, filename, marker in _persistent_specs(args, cluster_view=cluster_view):
            cmd = ["rhl-ps-persistent", "--json", "--level", "2"]
            if filename:
                cmd.extend(["--file", filename])
            if marker:
                cmd.extend(["--marker", marker])
            cmd.append(root)
            persistent_rows = (
                _persistent_row(row, service, cluster, root=root)
                for row in iter_ndjson(run_remote_capture(ssh_host, *cmd))
            )
            _merge_rows(rows, (row for row in persistent_rows if _persistent_row_matches_filters(row, args)))

    if args.json:
        _emit_json(rows)
    else:
        _table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
