file(name="pypi-readme", source="README.md")
# With `generate_setup=False`, setuptools reads this pyproject directly (version via setuptools-scm).
file(name="client-pyproject", source="pyproject.toml")
python_requirements(name="client-requirements", source="pyproject.toml", resolve="client-resolve")
python_distribution(
    name="client-whl",
    dependencies=[":client-pyproject", ":pypi-readme", "./src:openapi-spec", "./src:py-typed", "./src:scm-version"],
    provides=python_artifact(name="beetkeeper-api-client"),
    sdist=False,
    wheel=True,
    generate_setup=False,
)
