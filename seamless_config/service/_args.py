from __future__ import annotations

import argparse

SERVICES = ("hashserver", "database", "jobserver", "daskserver", "pure-daskserver")


def make_parser(prog, description, *, agent_mode=False):
    parser = argparse.ArgumentParser(prog=prog, description=description)
    parser.add_argument("--service", choices=SERVICES, required=agent_mode)
    parser.add_argument("--cluster")
    parser.add_argument("--project")
    parser.add_argument("--subproject")
    parser.add_argument("--stage")
    parser.add_argument("--substage")
    parser.add_argument("--mode", choices=("ro", "rw"), default="rw")
    parser.add_argument("--queue")
    parser.add_argument("--frontend-name")
    if agent_mode:
        parser.add_argument("--workdir")
    return parser
