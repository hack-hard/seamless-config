from __future__ import annotations

import json

from ._args import make_parser
from ._dispatch import remote_log_path, resolve

DISCLAIMER = """seamless-service-resolve reports what the currently-installed Seamless runtime
would compute for the given inputs. Outputs are not part of any stable contract:
keys, workdir paths, and host-selection logic may change between Seamless versions.
Tools that need stability should pin a Seamless version, or shell out to this
command on every invocation rather than caching its outputs."""


def main(argv=None) -> int:
    parser = make_parser(
        "seamless-service-resolve",
        "Resolve Seamless service identity and launcher paths.\n\n" + DISCLAIMER,
        agent_mode=True,
    )
    args = parser.parse_args(argv)
    key, ssh_hostname, config = resolve(args, from_cwd=args.workdir is not None)
    meta = config.get("meta", {})
    payload = {
        "key": key,
        "ssh_hostname": ssh_hostname,
        "workdir": config.get("workdir"),
        "log_path": remote_log_path(key),
    }
    payload.update(meta)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
