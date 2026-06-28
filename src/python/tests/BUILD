python_test_utils(
    name="base-pytest-utils",
    dependencies=["//src/python/beetkeeper:beetkeeper", "//:dev-requirements", "//src/python:app-requirements"],
)
# `skip_tests=True` keeps Pants' own pytest from running these targets under `pants test`; testing
# is handled exclusively by the `//:pytest` `test_shell_command` (uv-managed pytest). NOTE: the
# `[pytest].skip` subsystem option does NOT do this — it is not consulted by the test goal; only
# this per-target field is. Applies recursively to `python_tests` in subdirectories.
__defaults__({python_tests: dict(dependencies=["//src/python/tests:base-pytest-utils"], skip_tests=True)})
python_tests()
shell_source(name="tests-entrypoint", source="tests_entrypoint.sh")
