from __future__ import annotations

from ._args import make_parser
from ._dispatch import run_remote, resolve


def main(argv=None) -> int:
    parser = make_parser("seamless-service-logs", "Print Seamless service logs.")
    parser.add_argument("--tail", type=int)
    args = parser.parse_args(argv)
    if not args.service:
        parser.error("--service is required")
    key, ssh_host, _ = resolve(args, from_cwd=True)
    cmd = ["rhl-logs", key]
    if args.tail is not None:
        cmd.extend(["--tail", str(args.tail)])
    return run_remote(ssh_host, *cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
