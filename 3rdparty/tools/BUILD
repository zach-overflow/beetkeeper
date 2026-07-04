# The raw requirements file as a materializable `file` (so the resolve-consistency test under
# `src/integration_tests/meta_tests` can read it inside the Pants pytest sandbox; it's a dep of that test target).
file(name="tools-resolve-requirements-file", source="tools-resolve-requirements.txt")
python_requirements(
    name="tools-requirements",
    source="tools-resolve-requirements.txt",
    resolve="tools-resolve",
    # https://www.pantsbuild.org/stable/reference/targets/python_requirements#module_mapping
    module_mapping={"pydantic": ["pydantic", "pydantic.mypy"]},
)
