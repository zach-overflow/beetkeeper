# Subtree default: separate resolve so `beets` has one owner per resolve, keeping import inference unambiguous.
__defaults__(
    {(python_sources, python_tests, python_test_utils, python_requirements): dict(resolve="beetkeeper-resolve")}
)

file(name="pypi-readme", source="README.md")
# With `generate_setup=False`, setuptools reads this pyproject directly (version via setuptools-scm).
file(name="plugin-pyproject", source="pyproject.toml")
python_requirements(name="plugin-requirements", source="pyproject.toml")
python_distribution(
    name="plugin-whl",
    dependencies=[
        ":plugin-pyproject",
        ":plugin-requirements",
        ":pypi-readme",
        "./beetkeeper_plugin:beetkeeper_plugin",
        "./beetkeeper_plugin:scm-version",
        "!src/python:app-requirements",
    ],
    provides=python_artifact(name="beetkeeper-plugin"),
    sdist=False,
    wheel=True,
    generate_setup=False,
)
