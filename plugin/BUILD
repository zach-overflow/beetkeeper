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
        "./src/beetsplug/beetkeeper_plugin:beetkeeper_plugin",
        "./src/beetsplug/beetkeeper_plugin:scm-version",
        # Both distributions share one resolve, so `beets`/`pydantic`/`requests` have two requirement owners;
        # excluding the app's keeps import inference unambiguous.
        "!//beetkeeper-core:app-requirements",
    ],
    provides=python_artifact(name="beetkeeper-plugin"),
    sdist=False,
    wheel=True,
    generate_setup=False,
)
