from __future__ import annotations

from ._args import make_parser
from ._dispatch import run_remote, resolve


def main(argv=None) -> int:
    parser = make_parser("seamless-service-inspect", "Inspect Seamless service launcher state.")
    args = parser.parse_args(argv)
    if not args.service:
        parser.error("--service is required")
    key, ssh_host, _ = resolve(args, from_cwd=True)
    return run_remote(ssh_host, "rhl-inspect", key).returncode


if __name__ == "__main__":
    raise SystemExit(main())
