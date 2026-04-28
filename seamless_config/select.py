from typing import Optional

PROJECT_TOPLEVEL = "__TOPLEVEL__"

_current_cluster: Optional[str] = None
_current_project: Optional[str] = None
_current_subproject: Optional[str] = None
_current_stage: Optional[str] = None
_current_substage: Optional[str] = None
_current_execution: str = "process"
_current_queue: Optional[str] = None
_current_remote: Optional[str] = None
_current_persistent: Optional[bool] = None
_current_record: bool = False
_current_node: Optional[str] = None
_current_nparallel: Optional[int] = None
_execution_source: Optional[str] = None  # "command" or "manual"
_queue_source: Optional[str] = None  # "command" or "manual"
_queue_cluster: Optional[str] = None
_remote_source: Optional[str] = None  # "command" or "manual"
_persistent_source: Optional[str] = None  # "command" or "manual"
_record_source: Optional[str] = None  # "command" or "manual"
_node_source: Optional[str] = None  # "command" or "manual"
_execution_command_seen: bool = False
_persistent_command_seen: bool = False
_record_command_seen: bool = False

EXECUTION_MODES = ("process", "spawn", "remote")
REMOTE_TARGETS = (None, "daskserver", "jobserver")

from . import ConfigurationError


def _validate(s, name):
    if s.find("--") > -1:
        raise ValueError(f"{name} cannot contain '--'")
    if s.find("STAGE-") > -1:
        raise ValueError(f"{name} cannot contain 'STAGE-'")
    if name != "subproject":
        if s.find("/") > -1:
            raise ValueError(f"{name} cannot contain '/'")


def select_cluster(cluster):
    global _current_cluster, _current_queue, _queue_source, _queue_cluster
    if cluster is not None:
        _validate(cluster, "cluster")
    if cluster != _current_cluster:
        _current_queue = None
        _queue_source = None
        _queue_cluster = None
    _current_cluster = cluster


def select_project(project):
    global _current_project
    _validate(project, "project")
    _current_project = project


def select_subproject(subproject):
    global _current_subproject
    if subproject is not None:
        _validate(subproject, "subproject")
    _current_subproject = subproject


def select_stage(stage):
    global _current_stage
    if stage is not None:
        _validate(stage, "stage")
    _current_stage = stage


def select_substage(substage):
    global _current_substage
    if substage is not None:
        _validate(substage, "substage")
    _current_substage = substage


def select_execution(execution: str, *, source: str = "manual") -> None:
    global _current_execution, _execution_source, _execution_command_seen
    if not isinstance(execution, str):
        raise ValueError("execution must be a string")
    if execution not in EXECUTION_MODES:
        valid = ", ".join(EXECUTION_MODES)
        raise ValueError(f"execution must be one of: {valid}")
    _current_execution = execution
    _execution_source = source
    if source == "command":
        _execution_command_seen = True


def select_persistent(persistent: bool, *, source: str = "manual") -> None:
    global _current_persistent, _persistent_source, _persistent_command_seen
    if not isinstance(persistent, bool):
        raise ValueError("persistent must be a boolean")
    _current_persistent = persistent
    _persistent_source = source
    if source == "command":
        _persistent_command_seen = True


def select_record(record: bool, *, source: str = "manual") -> None:
    global _current_record, _record_source, _record_command_seen
    if not isinstance(record, bool):
        raise ValueError("record must be a boolean")
    _current_record = record
    _record_source = source
    if source == "command":
        _record_command_seen = True
    try:
        from seamless_transformer.record_runtime import invalidate_record_mode_cache

        invalidate_record_mode_cache()
    except Exception:
        pass


def select_queue(queue: str, *, source: str = "manual") -> None:
    global _current_queue, _queue_source, _queue_cluster
    if not isinstance(queue, str):
        raise ValueError("queue must be a string")
    cluster = _current_cluster
    if cluster is None:
        raise ValueError("Cannot select a queue without selecting a cluster first")
    from .cluster import get_cluster

    try:
        clus = get_cluster(cluster)
    except KeyError:
        raise ValueError(f"Unknown cluster '{cluster}'") from None
    queues = clus.queues
    if not queues:
        raise ValueError(f"Cluster '{cluster}' has no queues")
    if queue not in queues:
        raise ValueError(f"Cluster '{cluster}' has no queue '{queue}'")
    _current_queue = queue
    _queue_source = source
    _queue_cluster = cluster


def select_remote(remote: Optional[str], *, source: str = "manual") -> None:
    global _current_remote, _remote_source
    if remote is not None and not isinstance(remote, str):
        raise ValueError("remote must be a string or null")
    if remote not in REMOTE_TARGETS:
        valid = ", ".join([target for target in REMOTE_TARGETS if target is not None])
        raise ValueError(f"remote must be one of: None, {valid}")
    _current_remote = remote
    _remote_source = source


def select_node(node: Optional[str], *, source: str = "manual") -> None:
    global _current_node, _node_source
    if node is not None:
        if not isinstance(node, str):
            raise ValueError("node must be a string or null")
        if not node.strip():
            raise ValueError("node must not be empty")
    _current_node = node
    _node_source = source


def select_nparallel(nparallel: int) -> None:
    global _current_nparallel
    if isinstance(nparallel, bool) or not isinstance(nparallel, int) or nparallel < 1:
        raise ValueError("nparallel must be a positive integer")
    _current_nparallel = nparallel


def get_stage():
    return _current_stage


def get_selected_project() -> Optional[str]:
    return _current_project


def get_execution() -> str:
    if _execution_source is None and _current_cluster is not None:
        return "remote"
    return _current_execution


def execution_was_set_explicitly() -> bool:
    return _execution_source is not None


def execution_command_seen() -> bool:
    return _execution_command_seen


def persistent_was_set_explicitly() -> bool:
    return _persistent_source is not None


def get_persistent(cluster: Optional[str] = None) -> bool:
    if _current_persistent is not None:
        return _current_persistent
    if cluster is None:
        cluster = _current_cluster
    return bool(cluster)


def get_record() -> bool:
    return _current_record


def get_queue(cluster: Optional[str] = None) -> Optional[str]:
    if cluster is None:
        cluster = _current_cluster
    if cluster is None:
        return None
    if _current_queue is None:
        return None
    if _queue_cluster != cluster:
        return None
    from .cluster import get_cluster

    try:
        clus = get_cluster(cluster)
    except KeyError:
        return None
    queues = clus.queues
    if not queues or _current_queue not in queues:
        return None
    return _current_queue


def get_remote() -> Optional[str]:
    return _current_remote


def get_node() -> Optional[str]:
    return _current_node


def get_nparallel() -> int:
    if _current_nparallel is None:
        raise ConfigurationError(
            "nparallel is not set. "
            "Add 'nparallel: <N>' to seamless.profile.yaml or call seamless_config.set_nparallel(N)."
        )
    return _current_nparallel


def check_remote_redundancy(cluster: str) -> Optional[str]:
    """
    Ensure that when remote is unset, a cluster does not expose both jobserver and daskserver on the same frontend.
    """
    remote = get_remote()
    if remote is not None:
        return remote
    from .cluster import get_cluster

    clus = get_cluster(cluster)
    found_jobserver = False
    found_daskserver = False
    for frontend in clus.frontends:
        if frontend.jobserver is not None:
            found_jobserver = True
        if frontend.daskserver is not None:
            found_daskserver = True
        if frontend.jobserver is not None and frontend.daskserver is not None:
            raise ConfigurationError(
                f"Cluster '{cluster}' frontend '{frontend.hostname}' has both jobserver and daskserver; in your seamless.profile.yaml, specify 'remote: jobserver' or 'remote: daskserver'"
            )
    if found_jobserver and found_daskserver:
        raise ConfigurationError(
            f"Cluster '{cluster}' exposes both jobserver and daskserver; in your seamless.profile.yaml, specify 'remote: jobserver' or 'remote: daskserver'"
        )
    if found_jobserver:
        return "jobserver"
    if found_daskserver:
        return "daskserver"
    return None


def reset_execution_before_load() -> None:
    global _execution_source, _execution_command_seen, _current_execution
    _execution_command_seen = False
    if _execution_source == "command":
        _execution_source = None
        _current_execution = "process"


def reset_queue_before_load() -> None:
    global _current_queue, _queue_source, _queue_cluster
    if _queue_source == "command":
        _current_queue = None
        _queue_cluster = None
        _queue_source = None


def reset_remote_before_load() -> None:
    global _current_remote, _remote_source
    if _remote_source == "command":
        _current_remote = None
        _remote_source = None


def reset_persistent_before_load() -> None:
    global _current_persistent, _persistent_source, _persistent_command_seen
    _persistent_command_seen = False
    if _persistent_source == "command":
        _persistent_source = None
        _current_persistent = None


def reset_record_before_load() -> None:
    global _current_record, _record_source, _record_command_seen
    _record_command_seen = False
    if _record_source == "command":
        _record_source = None
        _current_record = False
    try:
        from seamless_transformer.record_runtime import invalidate_record_mode_cache

        invalidate_record_mode_cache()
    except Exception:
        pass


def reset_node_before_load() -> None:
    global _current_node, _node_source
    if _node_source == "command":
        _node_source = None
        _current_node = None


def get_selected_cluster() -> Optional[str]:
    return _current_cluster


def get_current(
    cluster: Optional[str] = None,
    project: Optional[str] = None,
    subproject: Optional[str] = None,
    stage: Optional[str] = None,
    substage: Optional[str] = None,
):
    if cluster is None:
        cluster = _current_cluster
        if cluster is None:
            raise ConfigurationError("No cluster defined")

    if project is None:
        project = _current_project
        if project is None:
            raise ConfigurationError("No project defined")

    if subproject is None:
        subproject = _current_subproject

    if stage is None:
        stage = _current_stage

    if substage is None:
        substage = _current_substage

    return cluster, project, subproject, stage, substage
