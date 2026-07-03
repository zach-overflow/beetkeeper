# Everything Python under `src/beetsplug` belongs to `beetsplug-resolve` (see pants.toml). This subtree-wide
# default keeps the plugin's `beets`/`requests` requirements in a resolve separate from the app's, so `beets`
# has exactly one owner per resolve and import inference is unambiguous (no manual `#beets` deps needed).
__defaults__(
    {(python_sources, python_tests, python_test_utils, python_requirements): dict(resolve="beetsplug-resolve")}
)

# Build config for this distribution lives in `src/python/pyproject.toml` (co-located in the
# source root so it lands in the PEP 517 backend's working dir). With `generate_setup=False`,
# setuptools reads that file and resolves the version from `beetkeeper._version.__version__`.
file(name="plugin-pyproject", source="pyproject.toml")
python_requirements(name="plugin-requirements", source="pyproject.toml")
python_distribution(
    name="plugin-whl",
    dependencies=[
        ":plugin-pyproject",
        ":plugin-requirements",
        "./beetkeeper_plugin:beetkeeper_plugin",
        "!src/python:app-requirements",
    ],
    provides=python_artifact(name="beetkeeper-plugin"),
    sdist=False,
    wheel=True,
    generate_setup=False,
)
