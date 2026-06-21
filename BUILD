# https://www.pantsbuild.org/stable/docs/using-pants/validating-dependencies#dependencies-and-dependents
__dependencies_rules__(("*", "*"))

file(name="pyproject", source="pyproject.toml")
file(name="uv-lockfile", source="uv.lock")
file(name="license-file", source="LICENSE.txt")
uv_requirements(name="dev-requirements", source="pyproject.toml")
python_requirement(name="pytest-socket", requirements=["pytest-socket"])

# We use this instead of the standard pants pytest subsystem, so we can use
# pytest plugins without having to manage an entire separate pytest resolve.
# https://www.pantsbuild.org/stable/reference/subsystems/pytest#requirements
test_cmd(
    name="pytest",
    command="uv run --all-groups pytest -vv ./src/python/tests",
    execution_dependencies=["//:pytest-socket"],
)


docker_image(
    name="beetkeeper-app-image",
    source="Dockerfile",
    target_stage="app",
    context_root="",
    image_tags=["app"],
    dependencies=[
        "src/python:dist-pyproject",
        ":pyproject",
        ":uv-lockfile",
        ":license-file",
        "src/python:lib-source-files",
    ],
)

docker_image(
    name="beetkeeper-test-image",
    source="Dockerfile",
    target_stage="test",
    image_tags=["test"],
    dependencies=[
        ":beetkeeper-app-image",
        "build_scripts:build_scripts",
        "hooks:hooks-scripts",
        "src/python:test-files",
    ],
)
