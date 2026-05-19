from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from platformdirs import PlatformDirs

import yaml  # type: ignore

from . import get_workdir
from .cluster import define_clusters as register_clusters
from .select import (
    PROJECT_TOPLEVEL,
    get_stage,
    reset_node_before_load,
    reset_record_before_load,
    select_nparallel,
    select_node,
    get_selected_project,
    reset_execution_before_load,
    reset_persistent_before_load,
    reset_queue_before_load,
    reset_remote_before_load,
    select_cluster,
    select_execution,
    select_persistent,
    select_project,
    select_queue,
    select_record,
    select_remote,
    select_subproject,
)
from .tools import define_tools

TOOLS_FILENAME = "tools.yaml"
CONFIG_FILENAMES: tuple[str, str] = ("seamless.yaml", "seamless.profile.yaml")
INHERIT_COMMAND = "inherit_from_parent"
COMMAND_LIST_EXAMPLE = "- project: myproject"

_clusters: dict[str, Any] = {}
SEAMLESS_CACHE_CLUSTER = "__SEAMLESS_CACHE__"


@dataclass(frozen=True)
class CommandSpec:
    handler: Callable[[Any, Path], None]
    priority: bool = False


@dataclass
class CommandInvocation:
    name: str
    argument: Any
    spec: CommandSpec
    source: Path

    @property
    def priority(self) -> bool:
        return self.spec.priority

    def execute(self) -> None:
        self.spec.handler(self.argument, self.source)


@dataclass(frozen=True)
class StageBlock:
    stage: str
    entries: list[Any]


_tools_loaded = False


# Tool definition
def load_tools() -> dict:
    """
    Load tool definitions from tools.yaml and register them inside seamless_config.tools.
    """
    global _tools_loaded
    if _tools_loaded:
        return
    _tools_loaded = True
    tools_file = Path(__file__).with_name(TOOLS_FILENAME)
    with tools_file.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a mapping in {tools_file}, found {type(data).__name__}"
        )

    define_tools(data)
    return data


# Command language
def _handle_cluster(value: Any, source: Path) -> None:
    if not isinstance(value, str) and value is not None:
        raise ValueError(f"{source}: 'cluster' command expects a string value or null")
    select_cluster(value)


def _handle_execution(value: Any, source: Path) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{source}: 'execution' command expects a string value")
    select_execution(value, source="command")


def _handle_queue(value: Any, source: Path) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{source}: 'queue' command expects a string value")
    select_queue(value, source="command")


def _handle_remote(value: Any, source: Path) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{source}: 'remote' command expects a string value or null")
    select_remote(value, source="command")


def _handle_persistent(value: Any, source: Path) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{source}: 'persistent' command expects a boolean value")
    select_persistent(value, source="command")


def _handle_record(value: Any, source: Path) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{source}: 'record' command expects a boolean value")
    select_record(value, source="command")


def _handle_project(value: Any, source: Path) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{source}: 'project' command expects a string value")
    select_project(value)


def _handle_subproject(value: Any, source: Path) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{source}: 'subproject' command expects a string value")
    select_subproject(value)


def _handle_nparallel(value: Any, source: Path) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{source}: 'nparallel' command expects a positive integer")
    select_nparallel(value)


def _handle_node(value: Any, source: Path) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{source}: 'node' command expects a string value or null")
    select_node(value, source="command")


def _handle_clusters(value: Any, source: Path) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{source}: 'clusters' command expects a mapping")
    _clusters.update(value)


COMMAND_SPECS: dict[str, CommandSpec] = {
    "cluster": CommandSpec(handler=_handle_cluster),
    "execution": CommandSpec(handler=_handle_execution),
    "queue": CommandSpec(handler=_handle_queue),
    "remote": CommandSpec(handler=_handle_remote),
    "persistent": CommandSpec(handler=_handle_persistent),
    "record": CommandSpec(handler=_handle_record),
    "project": CommandSpec(handler=_handle_project),
    "subproject": CommandSpec(handler=_handle_subproject),
    "nparallel": CommandSpec(handler=_handle_nparallel),
    "node": CommandSpec(handler=_handle_node),
    "clusters": CommandSpec(handler=_handle_clusters, priority=True),
}


_DEFAULT_CLUSTERS_YAML = """\
# Seamless cluster configuration
# 'local_cluster' is an alias that points to the active local cluster name.
local_cluster: local

local:
  type: local
  frontends:
    - hashserver:
        bufferdir: {bufferdir}
      database:
        database_dir: {database_dir}

# --- Example: remote Slurm cluster ---
# Uncomment and fill in to enable a remote HPC cluster.
#
# local_cluster: mycluster   # make mycluster the default local cluster
#
# mycluster:
#   tunnel: true              # connect via SSH tunnel
#   type: slurm               # local | slurm | oar
#   workers: 4                # number of workers for spawn/jobserver mode
#   frontends:
#     - hostname: login.mycluster.example
#       ssh_hostname: login.mycluster.example   # optional SSH override
#       hashserver:
#         bufferdir: /scratch/seamless/buffers
#         conda: hashserver
#         network_interface: 0.0.0.0
#         port_start: 60100
#         port_end: 60199
#       database:
#         database_dir: /scratch/seamless/db
#         conda: seamless-database
#         network_interface: 0.0.0.0
#         port_start: 60200
#         port_end: 60299
#       daskserver:
#         network_interface: 0.0.0.0
#         port_start: 60300
#         port_end: 60399
#   default_queue: default
#   queues:
#     default:
#       conda: seamless-dask
#       walltime: "01:00:00"
#       cores: 16
#       memory: 32000MB
#       tmpdir: /tmp
#       maximum_jobs: 20
#       unknown_task_duration: 1m
#       target_duration: 10m
#       lifetime_stagger: 4m
#     highmem:
#       TEMPLATE: default     # inherit all fields from 'default', then override
#       cores: 4
#       memory: 128000MB
"""


_PLATFORM_DIRS = PlatformDirs(appname="seamless", appauthor="sjdv1982")


def _create_default_config(config_base: Path, bufferdir: Path, database_dir: Path) -> None:
    clusters_file = config_base / "clusters.yaml"
    bufferdir.mkdir(parents=True, exist_ok=True)
    database_dir.mkdir(parents=True, exist_ok=True)
    clusters_file.write_text(
        _DEFAULT_CLUSTERS_YAML.format(
            bufferdir=bufferdir,
            database_dir=database_dir,
        ),
        encoding="utf-8",
    )


def _has_cluster_config(directory: Path) -> bool:
    return (directory / "clusters.yaml").is_file() or any(
        (directory / "clusters").glob("*.yaml")
    )


def get_seamless_config_paths() -> Path | None:
    import warnings

    if env_override := os.environ.get("SEAMLESS_CONFIG_DIR"):
        config_dir = Path(env_override)
        if not config_dir.exists():
            raise FileNotFoundError(
                f"SEAMLESS_CONFIG_DIR does not exist: {config_dir}"
            )
        if not _has_cluster_config(config_dir):
            raise FileNotFoundError(
                f"No cluster config found in SEAMLESS_CONFIG_DIR: {config_dir}"
            )
        return config_dir

    legacy_dir = Path.home() / ".seamless"
    platform_dir = Path(_PLATFORM_DIRS.user_config_dir)

    legacy_has = _has_cluster_config(legacy_dir)
    platform_has = _has_cluster_config(platform_dir)

    if legacy_has and platform_has:
        raise ValueError(
            f"Conflicting cluster configs found in both '{legacy_dir}' and "
            f"'{platform_dir}'. Remove one or set SEAMLESS_CONFIG_DIR."
        )

    if platform_has:
        return platform_dir

    if legacy_has:
        warnings.warn(
            f"~/.seamless is deprecated as the config location. "
            f"Migrate your config to '{platform_dir}' and run 'seamless-config-create'.",
            DeprecationWarning,
            stacklevel=2,
        )
        return legacy_dir

    warnings.warn(
        f"No global Seamless cluster config found in '{platform_dir}'. "
        "Cluster definitions must be provided inline. "
        "Run 'seamless-config-create' to create a default config.",
        UserWarning,
        stacklevel=2,
    )
    return None


def create_config() -> None:
    """Create a default Seamless config in the platform config directory."""
    legacy_dir = Path.home() / ".seamless"
    platform_dir = Path(_PLATFORM_DIRS.user_config_dir)
    env_override = os.environ.get("SEAMLESS_CONFIG_DIR")

    locations_to_check = (
        [Path(env_override)] if env_override else []
    ) + [legacy_dir, platform_dir]

    for loc in locations_to_check:
        if _has_cluster_config(loc):
            raise FileExistsError(
                f"Existing cluster config found in '{loc}'. Remove it first."
            )

    config_dir = Path(env_override) if env_override else platform_dir
    config_dir.mkdir(parents=True, exist_ok=True)
    _create_default_config(
        config_dir,
        Path(_PLATFORM_DIRS.user_cache_dir),
        Path(_PLATFORM_DIRS.user_data_dir),
    )
    print(f"Created default Seamless config in '{config_dir}'.")


def _load_clusters() -> dict[str, Any]:
    """
    Load cluster definitions from $XDG_CONFIG_HOME/seamless/clusters.yaml
    and $XDG_CONFIG_HOME/seamless/clusters/*.yaml into _clusters.
    """
    global _clusters
    config_dir = get_seamless_config_paths()
    if config_dir is None:
        _clusters = {}
        return _clusters
    clusters_path_yaml = config_dir / "clusters.yaml"
    clusters_pathdir = config_dir / "clusters"
    sub_yamls = clusters_pathdir.glob("*.yaml")
    data: dict[str, Any] = {}
    for clusters_path in [clusters_path_yaml] + list(sub_yamls):
        if clusters_path.is_file():
            with clusters_path.open("r", encoding="utf-8") as handle:
                data.update(yaml.safe_load(handle) or {})
    if not isinstance(data, dict):
        raise ValueError(f"{config_dir}: expected a mapping with cluster definitions")
    _clusters = data
    return _clusters


# File location and parsing
def load_config_files() -> None:
    """
    Load Seamless configuration files and execute their commands.
    """
    reset_execution_before_load()
    reset_persistent_before_load()
    reset_queue_before_load()
    reset_remote_before_load()
    reset_record_before_load()
    reset_node_before_load()
    load_tools()
    if _load_seamless_cache_config():
        return
    _load_clusters()
    commands = _build_command_invocations(_collect_command_entries())
    priority_commands = [cmd for cmd in commands if cmd.priority]
    non_priority_commands = [cmd for cmd in commands if not cmd.priority]

    for command in priority_commands:
        command.execute()

    register_clusters(_clusters)

    for command in non_priority_commands:
        command.execute()


def _load_seamless_cache_config() -> bool:
    from . import get_seamless_cache
    from .select import select_execution, select_persistent

    cache_dir = get_seamless_cache()
    if cache_dir is None:
        return False

    synthetic_clusters = {
        "local_cluster": SEAMLESS_CACHE_CLUSTER,
        SEAMLESS_CACHE_CLUSTER: {
            "type": "local",
            "frontends": [
                {
                    "hashserver": {"bufferdir": cache_dir},
                    "database": {"database_dir": cache_dir},
                }
            ],
        },
    }
    register_clusters(synthetic_clusters)
    select_cluster(SEAMLESS_CACHE_CLUSTER)
    if get_selected_project() is None:
        select_project(PROJECT_TOPLEVEL)
    select_execution("process")
    select_persistent(True)
    return True


def _collect_command_entries() -> list[tuple[Path, Any]]:
    commands_by_directory: list[list[tuple[Path, Any]]] = []
    current_dir = Path(get_workdir()).resolve()
    while True:
        directory_entries: list[tuple[Path, Any]] = []
        inherit = False
        for filename in CONFIG_FILENAMES:
            yaml_path = current_dir / filename
            if not yaml_path.is_file():
                continue
            entries = _read_yaml_list(yaml_path)
            directory_entries.extend((yaml_path, entry) for entry in entries)
            if _list_contains_inherit(entries):
                inherit = True
        commands_by_directory.append(directory_entries)
        if not inherit:
            break
        parent = current_dir.parent
        if parent == current_dir:
            break
        current_dir = parent
    commands: list[tuple[Path, Any]] = []
    for directory_entries in reversed(commands_by_directory):
        commands.extend(directory_entries)
    return commands


def _read_yaml_list(path: Path) -> list[Any]:
    with path.open("r", encoding="utf-8") as handle:
        content = yaml.safe_load(handle)
    if not isinstance(content, list):
        raise ValueError(
            f"{path}: expected a YAML list of commands. Example:\n{COMMAND_LIST_EXAMPLE}"
        )
    return content


def _list_contains_inherit(entries: Sequence[Any]) -> bool:
    return any(_extract_command_name(entry) == INHERIT_COMMAND for entry in entries)


def _build_command_invocations(
    entries: Iterable[tuple[Path, Any]],
) -> list[CommandInvocation]:
    commands: list[CommandInvocation] = []
    for path, entry in entries:
        name, argument = _parse_command_entry(entry, path)
        if name == INHERIT_COMMAND:
            continue
        if name == "stage":
            commands.extend(_expand_stage_commands(argument, path))
            continue
        spec = COMMAND_SPECS.get(name)
        if spec is None:
            raise ValueError(f"{path}: unknown command '{name}'")
        commands.append(
            CommandInvocation(name=name, argument=argument, spec=spec, source=path)
        )
    return commands


def _parse_command_entry(entry: Any, source: Path) -> tuple[str, Any]:
    if isinstance(entry, str):
        return entry, None
    if isinstance(entry, dict) and len(entry) == 1:
        key = next(iter(entry))
        if not isinstance(key, str):
            raise ValueError(f"{source}: command names must be strings")
        value = entry[key]
        stage_block = _maybe_build_stage_block(key, value, source)
        if stage_block is not None:
            return "stage", stage_block
        return key, value
    raise ValueError(
        f"{source}: commands must be defined as strings or single-key mappings"
    )


def _maybe_build_stage_block(key: str, value: Any, source: Path) -> StageBlock | None:
    prefix = "stage"
    if not key.startswith(prefix):
        return None
    remainder = key[len(prefix) :].strip()
    if not remainder:
        return None
    stage_name = remainder
    if not isinstance(value, list):
        raise ValueError(
            f"{source}: 'stage {stage_name}' must be followed by a YAML list of commands"
        )
    return StageBlock(stage=stage_name, entries=list(value))


def _expand_stage_commands(block: StageBlock, source: Path) -> list[CommandInvocation]:
    current_stage = get_stage()
    if current_stage != block.stage:
        return []
    nested_entries = [(source, entry) for entry in block.entries]
    return _build_command_invocations(nested_entries)


def _extract_command_name(entry: Any) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict) and len(entry) == 1:
        key = next(iter(entry))
        if isinstance(key, str):
            return key
    return None
