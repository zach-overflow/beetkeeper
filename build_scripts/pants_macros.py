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
        "//src/beetsplug:plugin-whl",
        "//src/beetsplug:plugin-pyproject",
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


def cli(name: str, entrypoint: str, **kwargs) -> None:
    """Macro for creating a CLI binary of beetkeeper, packaged as a PEX scie."""
    pex_tgt_name = f"{name}.pex-binary"
    tags = kwargs.pop("tags", []) + ["cli"]
    dependencies = kwargs.pop("dependencies", [])
    pex_binary(
        name=pex_tgt_name,
        scie_name_style="platform-file-suffix",
        entry_point=entrypoint,
        venv_site_packages_copies=True,
        execution_mode="venv",
        output_path=name,
        strip_pex_env=False,
        extra_build_args=[
            "--build-properties",
            '{"build data": "here"}',  # TODO [later]: add any build metadata needed here, if any.
        ],
        include_requirements=True,
        include_sources=True,
        include_tools=True,
        # complete_plaforms=[],  # TODO: see if this is needed?
        scie="eager",
        tags=tags,
        dependencies=dependencies,
    )
    archive(
        name=f"{name}.archive",
        format="tar.gz",
        packages=[f":{pex_tgt_name}"],
        output_path=f"cli/{name}.tar.gz",
        tags=tags,
        **kwargs,
    )
