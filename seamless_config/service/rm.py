from __future__ import annotations

from ._args import make_parser
from ._dispatch import cluster_ssh_hostname, iter_ndjson, row_matches_cluster, run_local, run_local_capture, run_remote, run_remote_capture, resolve


def main(argv=None) -> int:
    parser = make_parser("seamless-service-rm", "Remove Seamless service launcher state.")
    parser.add_argument("--client", action="store_true")
    parser.add_argument("--server", action="store_true")
    args = parser.parse_args(argv)
    do_client = args.client or not (args.client or args.server)
    do_server = args.server or not (args.client or args.server)
    rc = 0
    if args.service:
        key, ssh_host, _ = resolve(args, from_cwd=True)
        if do_server:
            rc = max(rc, run_remote(ssh_host, "rhl-rm", "--server", key).returncode)
        if do_client:
            rc = max(rc, run_local("rhl-rm", "--client", key).returncode)
        return rc
    if not args.cluster:
        parser.error("--service or --cluster is required")
    ssh_host = cluster_ssh_hostname(args.cluster, frontend_name=args.frontend_name)
    if do_server:
        rows = [r for r in iter_ndjson(run_remote_capture(ssh_host, "rhl-ps", "--json")) if row_matches_cluster(r, args.cluster)]
        if rows:
            rc = max(rc, run_remote(ssh_host, "rhl-rm", "--server", *(row["key"] for row in rows)).returncode)
    if do_client:
        rows = [r for r in iter_ndjson(run_local_capture("rhl-ps", "--client", "--json")) if row_matches_cluster(r, args.cluster)]
        if rows:
            rc = max(rc, run_local("rhl-rm", "--client", *(row["key"] for row in rows)).returncode)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
