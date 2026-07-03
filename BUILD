# https://www.pantsbuild.org/stable/docs/using-pants/validating-dependencies#dependencies-and-dependents
__dependencies_rules__(("*", "*"))

file(name="pyproject", source="pyproject.toml")
file(name="uv-lockfile", source="uv.lock")
file(name="license-file", source="LICENSE.txt")
file(name="version-file", source="VERSION")
docker_image(
    name="beetkeeper-server-image",
    source="Dockerfile",
    target_stage="app",
    context_root="",
    registries=["@ghcr"],
    repository="zach-overflow/beetkeeper",
    # `latest` + the release semver. `env("RELEASE_TAG", "dev")` reads the env var the `pants` process runs
    # with (the release workflow exports the v-stripped version); non-release / local builds fall back to `dev`.
    image_tags=["latest", env("RELEASE_TAG", "dev")],
    dependencies=[
        "src/python:dist-pyproject",
        ":pyproject",
        ":uv-lockfile",
        ":license-file",
        "src/python:lib-source-files",
    ],
)

# TODO [later]: enable the packaging of beetkeeper as a standalone scie binary.
# cli(
#     name="beetkeeper-binary",
#     entrypoint="beetkeeper.main:cli",
#     dependencies=[
#         "src/python:beetkeeper-whl",
#         # "src/beetsplug:plugin-whl",
#     ],
# )
