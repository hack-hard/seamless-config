from copy import deepcopy
from typing import Any
import re

_tools: dict[str, dict] = {}

DOLLAR_RE = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*")


def define_tools(tools: dict[str, dict]):
    for toolname, tool in tools.items():
        try:
            ADDED = tool["ADDED"]
            assert isinstance(ADDED, list)
            for v in ADDED:
                assert isinstance(v, str)

            INJECTED = tool["INJECTED"]
            assert isinstance(INJECTED, list)
            for v in INJECTED:
                assert isinstance(v, str)

        except Exception as exc:
            raise ValueError(f"{toolname}: {type(exc).__name__}: {exc}")

        _tools[toolname] = deepcopy(tool)


def _configure_tool(tool: str, *, added: dict[str, Any], injected: dict[str, Any]):
    conf = _tools[tool]
    ADDED, INJECTED = conf["ADDED"], conf["INJECTED"]
    for k in ADDED:
        if k not in added:
            raise ValueError(f'"{k}" must be added')
    for k in INJECTED:
        if k not in injected:
            raise ValueError(f'"{k}" must be injected')

    result = deepcopy(added)
    for key0, value0 in conf.items():
        if key0 in ("ADDED", "INJECTED"):
            continue
        if key0.endswith("_template"):
            key = key0[: -len("_template")]
            value = value0
            for m in reversed(list(DOLLAR_RE.finditer(value0))):
                inj = injected[m.group()[1:]]
                start, end = m.span()
                value = value[:start] + str(inj) + value[end:]
        else:
            key = key0
            value = value0
        result[key] = value

    # Special cases: hostname, ssh_hostname, tunnel
    # => remove only for the actual local cluster so remote-http-launcher runs locally.
    # A cluster with type "local" may still live on a remote frontend and should
    # keep its hostname so the launcher uses SSH there and starts a LocalCluster.
    cluster = injected.get("CLUSTER")
    if cluster == get_local_cluster():
        result.pop("hostname")
        result.pop("ssh_hostname", None)
        result.pop("tunnel", None)

    # Special cases: tunnel
    # => remove if False
    if not result.get("tunnel"):
        result.pop("tunnel", None)

    return result


def _build_injected(mode: str, cluster: str, project, subproject, stage, substage):
    assert isinstance(mode, str) and mode in ("ro", "rw"), mode
    injected = {"CLUSTER": cluster, "MODE": mode}
    projectsubdir = "/" + project
    if subproject is not None:
        projectsubdir += "/" + subproject
    injected["PROJECTSUBDIR"] = projectsubdir
    stagedir = ""
    stagesubdir = ""
    if stage is not None:
        stagedir = "/STAGE-" + stage
        stagesubdir = stagedir
        if substage is not None:
            stagesubdir += "SUBSTAGE-" + substage
    injected["STAGEDIR"] = stagedir
    injected["STAGESUBDIR"] = stagesubdir
    return injected


from .cluster import get_cluster, get_local_cluster, Cluster, ClusterFrontend


def _prepare_tool(
    tool: str,
    mode: str,
    cluster,
    project,
    subproject,
    stage,
    substage,
    frontend_name,
) -> tuple[Cluster, ClusterFrontend, dict[str, str]]:
    from .select import get_current
    from . import ConfigurationError

    cluster, project, subproject, stage, substage = get_current(
        cluster, project, subproject, stage, substage
    )
    if subproject == "":
        subproject = None
    if stage == "":
        stage = None
    if substage == "":
        substage = None
    clus = get_cluster(cluster)
    for frontend in clus.frontends:
        if frontend_name is not None and frontend.hostname != frontend_name:
            continue
        if getattr(frontend, tool) is not None:
            break
    else:
        if frontend_name is not None:
            raise ConfigurationError(
                f"No frontend of cluster '{cluster}' with name '{frontend_name}' can support a {tool}"
            )
        else:
            raise ConfigurationError(
                f"No frontend of cluster '{cluster}' can support a {tool}"
            )
    injected = _build_injected(mode, cluster, project, subproject, stage, substage)
    return clus, frontend, injected


def configure_hashserver(
    mode: str,
    *,
    cluster=None,
    project=None,
    subproject=None,
    stage=None,
    frontend_name=None,
):

    clus, frontend, injected = _prepare_tool(
        "hashserver", mode, cluster, project, subproject, stage, None, frontend_name
    )
    assert frontend.hashserver is not None
    injected["BUFFERDIR"] = frontend.hashserver.bufferdir

    added = {}
    added["tunnel"] = clus.tunnel
    added["hostname"] = frontend.hostname
    if frontend.ssh_hostname is not None:
        added["ssh_hostname"] = frontend.ssh_hostname
    added["network_interface"] = frontend.hashserver.network_interface
    added["conda"] = frontend.hashserver.conda
    added["port_start"] = frontend.hashserver.port_start
    added["port_end"] = frontend.hashserver.port_end

    result = _configure_tool("hashserver", added=added, injected=injected)
    for key in ("network_interface", "conda", "port_start", "port_end"):
        if result.get(key) is None:
            result.pop(key, None)
    return result


def configure_database(
    mode: str,
    *,
    cluster=None,
    project=None,
    subproject=None,
    stage=None,
    frontend_name=None,
):

    clus, frontend, injected = _prepare_tool(
        "database", mode, cluster, project, subproject, stage, None, frontend_name
    )
    assert frontend.database is not None
    injected["DATABASE_DIR"] = frontend.database.database_dir

    added = {}
    added["tunnel"] = clus.tunnel
    added["hostname"] = frontend.hostname
    if frontend.ssh_hostname is not None:
        added["ssh_hostname"] = frontend.ssh_hostname
    added["network_interface"] = frontend.database.network_interface
    added["conda"] = frontend.database.conda
    added["port_start"] = frontend.database.port_start
    added["port_end"] = frontend.database.port_end

    result = _configure_tool("database", added=added, injected=injected)
    for key in ("network_interface", "conda", "port_start", "port_end"):
        if result.get(key) is None:
            result.pop(key, None)
    return result


def configure_jobserver(
    *,
    cluster=None,
    project=None,
    subproject=None,
    stage=None,
    substage=None,
    frontend_name=None,
):
    from .extern_clients import collect_remote_clients
    from .select import get_record

    dummy_mode = "rw"  # not used for this tool
    clus, frontend, injected = _prepare_tool(
        "jobserver",
        dummy_mode,
        cluster,
        project,
        subproject,
        stage,
        substage,
        frontend_name,
    )
    assert frontend.jobserver is not None
    assert clus.workers is not None

    added = {}
    added["workers"] = clus.workers
    added["tunnel"] = clus.tunnel
    added["hostname"] = frontend.hostname
    if frontend.ssh_hostname is not None:
        added["ssh_hostname"] = frontend.ssh_hostname
    added["network_interface"] = frontend.jobserver.network_interface
    added["conda"] = frontend.jobserver.conda
    added["port_start"] = frontend.jobserver.port_start
    added["port_end"] = frontend.jobserver.port_end

    remote_client_parameters = collect_remote_clients(clus.name)
    remote_client_parameters["record"] = get_record()
    added["file_parameters"] = remote_client_parameters

    return _configure_tool("jobserver", added=added, injected=injected)


def configure_daskserver(
    *,
    cluster=None,
    project=None,
    subproject=None,
    stage=None,
    substage=None,
    frontend_name=None,
):
    dummy_mode = "rw"  # not used for this tool
    from . import ConfigurationError
    from .select import get_node, get_queue, get_record

    clus, frontend, injected = _prepare_tool(
        "daskserver",
        dummy_mode,
        cluster,
        project,
        subproject,
        stage,
        substage,
        frontend_name,
    )
    assert frontend.daskserver is not None

    added = {}
    assert clus.type is not None
    if clus.type == "local":
        cluster_string = "distributed::LocalCluster"
    elif clus.type == "slurm":
        cluster_string = "dask_jobqueue::SLURMCluster"
    elif clus.type == "oar":
        cluster_string = "dask_jobqueue::OARCluster"
    else:
        raise ValueError(clus.type)
    added["cluster_string"] = cluster_string
    added["tunnel"] = clus.tunnel
    added["hostname"] = frontend.hostname
    if frontend.ssh_hostname is not None:
        added["ssh_hostname"] = frontend.ssh_hostname
    added["network_interface"] = frontend.daskserver.network_interface
    queue_name = get_queue(clus.name) or clus.default_queue
    queues = clus.queues or {}
    if queue_name is None:
        raise ConfigurationError(
            f"No queue selected and cluster '{clus.name}' has no default queue"
        )
    if queue_name not in queues:
        raise ConfigurationError(f"Cluster '{clus.name}' has no queue '{queue_name}'")
    queue = queues[queue_name]
    requested_node = get_node()
    added["conda"] = queue.conda
    added["port_start"] = frontend.daskserver.port_start
    added["port_end"] = frontend.daskserver.port_end

    # TODO: make queue parameters overrulable in seamless.profile.yaml (advanced use case)

    params = {}

    """
    #### B

    The following parameters are read from the status file "parameters" dict,
    and propagated into jobqueue. If marked as "optional", propagation only takes place if defined.

    Otherwise, if no default is specified, they are mandatory.

    - walltime
    - cores
    - memory
    - tmpdir. Propagated into both "local-directory" and "temp-directory". Default: /tmp
    - partition, propagated into "queue". Optional
    - job_extra_directives: Optional, but must be a list if defined. Example: ["-p grappe"]
    - project. Optional (e.g. "capsid")
    - memory_per_core_property_name. Optional.
    - job_script_prologue: Optional, but must be a list if defined.
    """

    params["walltime"] = queue.walltime
    params["exclusive"] = queue.exclusive
    params["cores"] = queue.cores
    params["job_cores"] = queue.job_cores
    if queue.cores is None and clus.type == "local":
        params["cores"] = clus.workers
    params["memory"] = queue.memory
    params["tmpdir"] = queue.tmpdir
    params["partition"] = queue.partition
    job_extra_directives = list(queue.job_extra_directives or [])
    resource_spec = None
    if requested_node is not None:
        if clus.type == "slurm":
            nodelist_flag = f"--nodelist={requested_node}"
            if nodelist_flag not in job_extra_directives:
                job_extra_directives.append(nodelist_flag)
        elif clus.type == "oar":
            job_extra_directives.extend(["-p", f"host='{requested_node}'"])
        else:
            raise ConfigurationError(
                f"Node selection is not supported for cluster type '{clus.type}'"
            )
    if queue.exclusive:
        if queue.cores is not None:
            # Case 1: fixed cores — job_cores equals cores
            params["job_cores"] = queue.cores
        else:
            # Case 2: whole-node — use scheduler-specific exclusive mechanism
            if clus.type == "slurm":
                if "--exclusive" not in job_extra_directives:
                    job_extra_directives.append("--exclusive")
            elif clus.type == "oar":
                resource_spec = "/nodes=1"
    if resource_spec is not None:
        params["resource_spec"] = resource_spec
    params["job_extra_directives"] = job_extra_directives or None
    params["project"] = queue.project
    params["memory_per_core_property_name"] = clus.memory_per_core_property_name
    params["job_script_prologue"] = queue.job_script_prologue
    params["worker_threads"] = queue.worker_threads
    params["processes"] = queue.processes

    """
    #### C

    The following parameters are read from the status file "parameters" dict,
    and propagated into Dask. If marked as "optional", propagation only takes place if defined.

    Otherwise, if no default is specified, they are mandatory.

    - unknown-task-duration => distributed.scheduler.unknown-task-duration. Default: 1m

    - target-duration => distributed.scheduler.target-duration. Default: 10m

    - internal-port-range => distributed.worker.port and distributed.nanny.port. Default: port-range command-line parameter

    - lifetime-stagger => distributed.worker.lifetime-stagger. Default: 4m

    - lifetime => distributed.worker.lifetime. Default: walltime minus lifetime-stagger minus 1m

    In case of default: Note that "walltime" is in hh:mm:ss format. All three values (walltime, lifetime-stagger and 1m) are understood by `dask.utils.parse_timedelta`. The subtraction result `td` can be converted to string using f"{int(td.total_seconds())}s"

    - dask-resources => distributed.worker.resources. Optional.
    """

    params["unknown-task-duration"] = queue.unknown_task_duration
    params["target-duration"] = queue.target_duration
    # params["internal-port-range"] = frontend.daskserver. ... # TODO
    params["lifetime-stagger"] = queue.lifetime_stagger
    params["lifetime"] = queue.lifetime
    params["dask-resources"] = queue.dask_resources
    params["interactive"] = queue.interactive
    params["maximum_jobs"] = queue.maximum_jobs

    # TODO: params["transformation_throttle"] = ...

    params["extra_dask_config"] = queue.extra_dask_config
    params["record"] = get_record()

    params = {k: v for k, v in params.items() if v is not None}
    added["file_parameters"] = params

    return _configure_tool("daskserver", added=added, injected=injected)


def configure_pure_daskserver(
    *,
    cluster=None,
    queue: str | None = None,
    frontend_name=None,
):
    from . import ConfigurationError
    from .select import get_node, get_queue, get_selected_cluster

    if cluster is None:
        cluster = get_selected_cluster()
    if cluster is None:
        raise ConfigurationError("No cluster defined")
    clus = get_cluster(cluster)
    for frontend in clus.frontends:
        if frontend_name is not None and frontend.hostname != frontend_name:
            continue
        if frontend.daskserver is not None:
            break
    else:
        if frontend_name is not None:
            raise ConfigurationError(
                f"No frontend of cluster '{cluster}' with name '{frontend_name}' can support a daskserver"
            )
        raise ConfigurationError(
            f"No frontend of cluster '{cluster}' can support a daskserver"
        )

    injected = {"CLUSTER": cluster}

    added = {}
    assert clus.type is not None
    if clus.type == "local":
        cluster_string = "distributed::LocalCluster"
    elif clus.type == "slurm":
        cluster_string = "dask_jobqueue::SLURMCluster"
    elif clus.type == "oar":
        cluster_string = "dask_jobqueue::OARCluster"
    else:
        raise ValueError(clus.type)
    added["cluster_string"] = cluster_string
    added["tunnel"] = clus.tunnel
    added["hostname"] = frontend.hostname
    if frontend.ssh_hostname is not None:
        added["ssh_hostname"] = frontend.ssh_hostname
    added["network_interface"] = frontend.daskserver.network_interface
    queue_name = queue or get_queue(cluster) or clus.default_queue
    queues = clus.queues or {}
    if queue_name is None:
        raise ConfigurationError(
            f"No queue selected and cluster '{clus.name}' has no default queue"
        )
    if queue_name not in queues:
        raise ConfigurationError(f"Cluster '{clus.name}' has no queue '{queue_name}'")
    queue_def = queues[queue_name]
    injected["QUEUE"] = queue_name
    requested_node = get_node()
    added["conda"] = queue_def.conda
    added["port_start"] = frontend.daskserver.port_start
    added["port_end"] = frontend.daskserver.port_end

    params = {}

    params["walltime"] = queue_def.walltime
    params["cores"] = queue_def.cores
    params["job_cores"] = queue_def.job_cores
    if queue_def.cores is None and clus.type == "local":
        params["cores"] = clus.workers
    params["memory"] = queue_def.memory
    params["tmpdir"] = queue_def.tmpdir
    params["partition"] = queue_def.partition
    job_extra_directives = list(queue_def.job_extra_directives or [])
    resource_spec = None
    if requested_node is not None:
        if clus.type == "slurm":
            nodelist_flag = f"--nodelist={requested_node}"
            if nodelist_flag not in job_extra_directives:
                job_extra_directives.append(nodelist_flag)
        elif clus.type == "oar":
            job_extra_directives.extend(["-p", f"host='{requested_node}'"])
        else:
            raise ConfigurationError(
                f"Node selection is not supported for cluster type '{clus.type}'"
            )
    if queue_def.exclusive and queue_def.cores is None and clus.type == "oar":
        resource_spec = "/nodes=1"
    params["job_extra_directives"] = job_extra_directives or None
    if resource_spec is not None:
        params["resource_spec"] = resource_spec
    params["project"] = queue_def.project
    params["memory_per_core_property_name"] = clus.memory_per_core_property_name
    params["job_script_prologue"] = queue_def.job_script_prologue
    worker_threads = queue_def.worker_threads
    if worker_threads is None:
        worker_threads = 2
    params["worker_threads"] = worker_threads
    params["processes"] = queue_def.processes

    params["unknown-task-duration"] = queue_def.unknown_task_duration
    params["target-duration"] = queue_def.target_duration
    params["lifetime-stagger"] = queue_def.lifetime_stagger
    params["lifetime"] = queue_def.lifetime
    params["dask-resources"] = queue_def.dask_resources
    params["interactive"] = queue_def.interactive
    params["maximum_jobs"] = queue_def.maximum_jobs
    if params["maximum_jobs"] is None and clus.type == "local":
        params["maximum_jobs"] = clus.workers
    params["pure_dask"] = True
    params["extra_dask_config"] = queue_def.extra_dask_config

    params = {k: v for k, v in params.items() if v is not None}
    added["file_parameters"] = params

    return _configure_tool("pure_daskserver", added=added, injected=injected)
