__dependencies_rules__(("*", "*"))

file(name="pyproject", source="pyproject.toml")
file(name="uv-lockfile", source="uv.lock")
file(name="license-file", source="LICENSE.txt")
file(name="version-file", source="VERSION")
file(name="dockerfile", source="Dockerfile")

# TODO: enable cross-platform PEX after https://github.com/pantsbuild/pants/issues/23339
pex_binary(
    name="bk",
    scie_name_style="platform-file-suffix",
    script="beetkeeper",
    venv_site_packages_copies=True,
    execution_mode="venv",
    output_path="bk",
    strip_pex_env=False,
    extra_build_args=[
        "--build-properties",
        '{"build data": "here"}',  # add any build metadata needed here, if needed.
    ],
    include_requirements=True,
    include_sources=True,
    include_tools=True,
    # complete_platforms=[
    #     "//3rdparty/platforms:linux-aarch64",
    #     "//3rdparty/platforms:linux-amd64", 
    #     "//3rdparty/platforms:macos-aarch64",
    #     "//3rdparty/platforms:macos-amd64",
    #     "//3rdparty/platforms:musl-aarch64",
    #     "//3rdparty/platforms:musl-amd64",
    # ],
    scie="eager",
    tags=["pex"],
    dependencies=["//src/python:app-requirements", "//src/python:beetkeeper-whl"],
)

docker_image(
    name="beetkeeper-server-image",
    source="Dockerfile",
    # target_stage="app",
    context_root="",
    registries=["@ghcr"],
    repository="zach-overflow/beetkeeper",
    # RELEASE_TAG is the v-stripped version exported by the release workflow; local builds fall back to `dev`.
    image_tags=["latest", env("RELEASE_TAG", "dev")],
    dependencies=[
        "src/python:dist-pyproject",
        ":pyproject",
        ":uv-lockfile",
        ":license-file",
        "src/python:beetkeeper-whl",
        "src/python:lib-source-files",
        "build_scripts:build_scripts"
    ],
)

# TODO [later]: enable packaging beetkeeper as a standalone scie binary.
# cli(
#     name="beetkeeper-binary",
#     entrypoint="beetkeeper.main:cli",
#     dependencies=[
#         "src/python:beetkeeper-whl",
#         # "src/beetsplug:plugin-whl",
#     ],
# )
