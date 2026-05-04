from __future__ import annotations

from ._args import make_parser
from ._dispatch import cluster_ssh_hostname, iter_ndjson, row_matches_cluster, run_remote, run_remote_capture, resolve


def main(argv=None) -> int:
    parser = make_parser("seamless-service-stop", "Stop Seamless services.")
    args = parser.parse_args(argv)
    if args.service:
        key, ssh_host, _ = resolve(args, from_cwd=True)
        return run_remote(ssh_host, "rhl-stop", key).returncode
    if not args.cluster:
        parser.error("--service or --cluster is required")
    ssh_host = cluster_ssh_hostname(args.cluster, frontend_name=args.frontend_name)
    rows = [r for r in iter_ndjson(run_remote_capture(ssh_host, "rhl-ps", "--json")) if row_matches_cluster(r, args.cluster)]
    if not rows:
        return 0
    return run_remote(ssh_host, "rhl-stop", *(row["key"] for row in rows)).returncode


if __name__ == "__main__":
    raise SystemExit(main())
