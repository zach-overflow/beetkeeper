# https://www.pantsbuild.org/stable/docs/writing-plugins/macros
_VALID_PLATFORMS = ("linux-amd64", "linux-arm64", "macos-amd64", "macos-arm64")


def test_cmd(
    name: str,
    command: str,
    execution_dependencies: list[str] | None = None,
    extra_tools: list[str] | None = None,
    **kwargs,
):
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
        extra_tools: Any additional system binaries required to run the given test command, in addition to the auto-included 'bash' and 'uv' tools.
    """
    protected_kwargs = set(["workdir", "log_output", "tools"])
    if illegal_kwargs := set(kwargs.keys()).intersection(protected_kwargs):
        raise ValueError(f"Invalid `test_cmd` call: remove the following protected kwargs: {sorted(illegal_kwargs)}")
    tags = kwargs.pop("tags", []) + ["test_cmd"]
    extra_execution_dependencies = execution_dependencies or []
    extra_tools = extra_tools or []
    builtin_exec_deps = [
        "//:pyproject",
        "//plugin:plugin-whl",
        "//plugin:plugin-pyproject",
        "//beetkeeper-core:app-requirements",
        "//beetkeeper-core:dist-pyproject",
        "//beetkeeper-core:lib-source-files",
        "//:uv-lockfile",
    ]
    test_shell_command(
        name=f"{name}",
        workdir="/",
        command=command,
        log_output=True,
        tools=sorted(set(["bash", "uv"] + extra_tools)),
        execution_dependencies=sorted(set(builtin_exec_deps + extra_execution_dependencies)),
        tags=tags,
    )


def app_server_pexes(complete_platforms: list[str], **kwargs):
    """Consolidated `pex_binary` target generator for the `beetkeeper` application pex / scie (binary)."""
    tags = kwargs.pop("tags", []) + ["app_server_pexes", "pex"]
    for platform in complete_platforms:
        if platform.split(":")[-1] not in _VALID_PLATFORMS:
            raise ValueError(f"unsupported complete platform {platform!r}; expected a target named one of {_VALID_PLATFORMS}")
        for is_scie in (False, True):
            _generate_application_pex(complete_platform=platform, is_scie=is_scie, tags=tags, **kwargs)


def _generate_application_pex(complete_platform: str, is_scie: bool, tags: list[str], **kwargs):
    """The internal helper called once per distinct output PEX / SCIE by `app_server_pexes` macro (above)."""
    plat_name = complete_platform.split(":")[-1]
    tgt_name = _generate_application_pex_target_name(plat_name=plat_name, is_scie=is_scie)
    scie_kwargs = dict(
        scie="lazy",
        scie_pbs_stripped=True,
        scie_platform=[_translate_platform_name_to_scie_style(plat_name)],
        scie_name_style="platform-file-suffix",
        scie_hash_alg="sha256",
    ) if is_scie else dict()

    pex_binary(
        name=tgt_name,
        script="beetkeeper",
        output_path=f"standalone/{plat_name}/beetkeeper" if is_scie else f"{tgt_name}.pex",
        include_requirements=True,
        include_sources=True,
        include_tools=False,  # TODO: make sure this is compat since it was `True` before writing this macro
        inherit_path="fallback",
        complete_platforms=[complete_platform],
        extra_build_args=[] if is_scie else ["--rc"],
        tags=tags + (["scie"] if is_scie else []),
        **scie_kwargs,
        **kwargs,
    )


def _generate_application_pex_target_name(plat_name: str, is_scie: bool) -> str:
    """Helper for generating the pants target name for the `app_server_pexes` macro above."""
    common_prefix = f"beetkeeper-{plat_name}"
    return f"{common_prefix}-{'standalone' if is_scie else 'pex'}"


def _translate_platform_name_to_scie_style(docker_style_platform_name: str) -> str:
    return {
        "current": "current",
        "linux-arm64": "linux-aarch64",
        "linux-amd64": "linux-x86_64",
        "macos-arm64": "macos-aarch64",
        "macos-amd64": "macos-x86_64",
    }[docker_style_platform_name]
