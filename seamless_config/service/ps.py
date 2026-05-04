from __future__ import annotations

import json
import subprocess
import sys

from ._args import make_parser
from ._dispatch import (
    cluster_ssh_hostname,
    iter_ndjson,
    row_matches_filters,
    run_local_capture,
    run_remote_capture,
    resolve,
)


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
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    return {
        "service": meta.get("service"),
        "cluster": meta.get("cluster"),
        "project": meta.get("project"),
        "stage": meta.get("stage"),
        "process": row.get("status"),
        "port": row.get("port"),
        "persistent": None,
        "size": None,
        "key": row.get("key"),
    }


def _persistent_row(row, service, cluster):
    name = row.get("path", "").rstrip("/").split("/")[-1]
    stage = name.removeprefix("STAGE-") if name.startswith("STAGE-") else None
    project = None if stage else name or None
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


def _known_clusters():
    from seamless_config.config_files import load_config_files
    from seamless_config.cluster import _clusters

    load_config_files()
    return list(_clusters)


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
    if args.server:
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

    rows.extend(_process_row(row) for row in process_rows if row_matches_filters(row, args))

    if args.persistent:
        requested_service = args.service
        for service in ("hashserver", "database"):
            if requested_service and requested_service != service:
                continue
            probe_args = args
            probe_args.service = service
            try:
                _key, ssh_host, config = resolve(probe_args, from_cwd=True)
            except Exception as exc:
                print(f"seamless-service-ps: persistent {service}: {exc}", file=sys.stderr)
                continue
            cmd = ["rhl-ps-persistent", "--json", "--level", "2"]
            if service == "database":
                cmd.extend(["--file", "seamless.db"])
            cmd.append(config["workdir"])
            rows.extend(_persistent_row(row, service, config.get("meta", {}).get("cluster")) for row in iter_ndjson(run_remote_capture(ssh_host, *cmd)))

    if args.json:
        _emit_json(rows)
    else:
        _table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
