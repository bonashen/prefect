from typing import Union, Iterable

import yaml

from prefect.run_configs.base import RunConfig
from prefect.utilities.filesystems import parse_path


class ECSRun(RunConfig):
    """Configure a flow-run to run as an ECS Task.

    Note: The functionality here is experimental, and may change between
    versions without notice. Use at your own risk.

    ECS Tasks are composed of task definitions and runtime parameters.

    Task definitions can be configured using either the `task_definition` or
    `task_definition_path` parameters. If neither is specified, the default
    configured on the agent will be used. At runtime this task definition will
    be registered once per flow version - subsequent runs of the same flow
    version will reuse the existing definition.

    Runtime parameters can be specified via `run_task_kwargs`. These will be
    merged with any runtime parameters configured on the agent when starting
    the task.

    Args:
        - task_definition (dict, optional): An in-memory task definition spec
            to use. See the [ECS.Client.register_task_definition][3] docs for
            more information on task definitions. Note that this definition
            will be stored directly in Prefect Cloud/Server - use
            `task_definition_path` instead if you wish to avoid this.
        - task_definition_path (str, optional): Path to a task definition spec
            to use. If a local path (no file scheme, or a `file`/`local`
            scheme), the task definition will be loaded on initialization and
            stored on the `ECSRun` object as the `task_definition` field.
            Otherwise the task definition will be loaded at runtime on the
            agent.  Supported runtime file schemes include (`s3`, `gcs`, and
            `agent` (for paths local to the runtime agent)).
        - image (str, optional): The image to use for this task. If not
            provided, will be either inferred from the flow's storage (if using
            `Docker` storage), or use the default configured on the agent.
        - env (dict, optional): Additional environment variables to set on the task.
        - cpu (int or str, optional): The amount of CPU available to the task. Can
            be ether an integer in CPU units (e.g. `1024`), or a string using
            vCPUs (e.g. `"1 vcpu"`). Note that ECS imposes strict limits on
            what values this can take, see the [ECS documentation][2] for more
            information.
        - memory (int or str, optional): The amount of memory available to the
            task. Can be ether an integer in MiB (e.g. `1024`), or a string
            with units (e.g. `"1 GB"`). Note that ECS imposes strict limits on
            what values this can take, see the [ECS documentation][2] for more
            information.
        - run_task_kwargs (dict, optional): Additional keyword arguments to
            pass to `run_task` when starting this task. See the
            [ECS.Client.run_task][3] docs for more information.
        - labels (Iterable[str], optional): An iterable of labels to apply to this
            run config. Labels are string identifiers used by Prefect Agents
            for selecting valid flow runs when polling for work

    Examples:

    Use the defaults set on the agent:

    ```python
    flow.run_config = ECSRun()
    ```

    Use the default task definition, but override the image and CPU:

    ```python
    flow.run_config = ECSRun(
        image="example/my-custom-image:latest",
        cpu="2 vcpu",
    )
    ```

    Use an explicit task definition stored in s3, but override the image and CPU:

    ```python
    flow.run_config = ECSRun(
        task_definition="s3://bucket/path/to/task.yaml",
        image="example/my-custom-image:latest",
        cpu="2 vcpu",
    )
    ```

    [1]: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/\
ecs.html#ECS.Client.register_task_definition

    [2]: https://docs.aws.amazon.com/AmazonECS/latest/userguide/task-cpu-memory-error.html

    [3]: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/\
ecs.html#ECS.Client.run_task
    """

    def __init__(
        self,
        *,
        task_definition: dict = None,
        task_definition_path: str = None,
        image: str = None,
        env: dict = None,
        cpu: Union[int, str] = None,
        memory: Union[int, str] = None,
        run_task_kwargs: dict = None,
        labels: Iterable[str] = None,
    ) -> None:
        super().__init__(labels=labels)

        if task_definition is not None and task_definition_path is not None:
            raise ValueError(
                "Cannot provide both `task_definition` and `task_definition_path`"
            )
        if task_definition_path is not None:
            parsed = parse_path(task_definition_path)
            if parsed.scheme == "file":
                with open(parsed.path) as f:
                    task_definition = yaml.safe_load(f)
                    task_definition_path = None

        if cpu is not None:
            cpu = str(cpu)
        if memory is not None:
            memory = str(memory)

        self.task_definition = task_definition
        self.task_definition_path = task_definition_path
        self.image = image
        self.env = env
        self.cpu = cpu
        self.memory = memory
        self.run_task_kwargs = run_task_kwargs
