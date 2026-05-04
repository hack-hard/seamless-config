from __future__ import annotations

import json
import os
import pathlib
import sys

from ._args import make_parser
from ._dispatch import cluster_ssh_hostname, iter_ndjson, row_matches_cluster, run_remote, run_remote_capture, resolve


def _client_json_path(key: str) -> pathlib.Path:
    base = os.environ.get("REMOTE_HTTP_LAUNCHER_DIR", "~/.remote-http-launcher")
    return pathlib.Path(base).expanduser() / "client" / f"{key}.json"


def _mark_client_stale(keys) -> None:
    for key in keys:
        path = _client_json_path(key)
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                continue
            data["status"] = "stale"
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(data), encoding="utf-8")
            tmp_path.replace(path)
        except OSError as exc:
            print(f"seamless-service-stop: could not mark {path} stale: {exc}", file=sys.stderr)
        except json.JSONDecodeError as exc:
            print(f"seamless-service-stop: malformed client state {path}: {exc}", file=sys.stderr)


def main(argv=None) -> int:
    parser = make_parser("seamless-service-stop", "Stop Seamless services.")
    args = parser.parse_args(argv)
    if args.service:
        key, ssh_host, _ = resolve(args, from_cwd=True)
        rc = run_remote(ssh_host, "rhl-stop", key).returncode
        if rc == 0:
            _mark_client_stale([key])
        return rc
    if not args.cluster:
        parser.error("--service or --cluster is required")
    ssh_host = cluster_ssh_hostname(args.cluster, frontend_name=args.frontend_name)
    rows = [r for r in iter_ndjson(run_remote_capture(ssh_host, "rhl-ps", "--json")) if row_matches_cluster(r, args.cluster)]
    if not rows:
        return 0
    keys = [row["key"] for row in rows]
    rc = run_remote(ssh_host, "rhl-stop", *keys).returncode
    if rc == 0:
        _mark_client_stale(keys)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
