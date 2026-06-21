# https://www.pantsbuild.org/stable/docs/writing-plugins/macros

def test_cmd(name: str, command: str, execution_dependencies: list[str] | None = None, **kwargs):
    """
    Wrapper for test targets invoked via `test_shell_command` targets, instead of their pantsbuild 'tool' alternative.
    We don't use the native pantsbuild tool for `pytest`, `mypy` or a few other things since they require 3rdparty dependencies,
    not shipped with pantsbuild. That in turn would require a separate resolve per tool, which is a nightmare, and complete overkill
    for this repo.

    Args:
        name: the name to set for the generated `run_shell_command` target.
        command: the command the target should run (as `bash -c '<command>'`: see https://www.pantsbuild.org/stable/reference/targets/shell_command#command)
        execution_dependencies: Any extra targets required for execution. These will be added with a number of 
            builtin values provided from the macro.
    """
    protected_kwargs = set(["workdir", "log_output", "tools"])
    if illegal_kwargs := set(kwargs.keys()).intersection(protected_kwargs):
        raise ValueError(f"Invalid `test_cmd` call: remove the following protected kwargs: {sorted(illegal_kwargs)}")
    tags = kwargs.pop("tags", []) + ["test_cmd"]
    extra_execution_dependencies = execution_dependencies or []
    builtin_exec_deps = [
        "//:dev-requirements",
        "//:pyproject",
        "//src/python:app-requirements",
        "//src/python:dist-pyproject",
        "//src/python:lib-source-files",
        "//src/python:test-files",
        "//:uv-lockfile",
    ]
    test_shell_command(
        name=f"{name}",
        workdir="/",
        command=command,
        log_output=True,
        tools=["bash", "uv"],
        execution_dependencies=sorted(set(builtin_exec_deps + extra_execution_dependencies)),
        tags=tags,
    )
