# `file` target so the resolve-consistency test can read the raw requirements in the pytest sandbox.
file(name="tools-resolve-requirements-file", source="tools-resolve-requirements.txt")
python_requirements(
    name="tools-requirements",
    source="tools-resolve-requirements.txt",
    resolve="tools-resolve",
    module_mapping={"pydantic": ["pydantic", "pydantic.mypy"]},
)
