from __future__ import annotations

from ._args import make_parser
from ._dispatch import run_remote, resolve


def main(argv=None) -> int:
    parser = make_parser("seamless-service-clear", "Clear persistent Seamless service state.")
    args = parser.parse_args(argv)
    if args.service not in ("hashserver", "database"):
        parser.error("--service must be hashserver or database")
    _key, ssh_host, config = resolve(args, from_cwd=True)
    workdir = config.get("workdir")
    if not workdir or workdir == "/tmp":
        parser.error("service has no clearable persistent workdir")
    return run_remote(ssh_host, "rhl-clear", workdir).returncode


if __name__ == "__main__":
    raise SystemExit(main())
