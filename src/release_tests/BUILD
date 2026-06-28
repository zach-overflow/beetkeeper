python_test_utils(
    name="release-test-utils",
    dependencies=[
        "//src/beetsplug:plugin-pyproject",  # The beetsplug pyproject.toml (has static version set)
        "//src/python/beetkeeper:beetkeeper",  # The beetkeeper server library (version set in `beetkeeper._version`)
        "//:dev-requirements",  # Common testing requirements
        "//src/python:app-requirements",  # beetkeeper app requirements for loading and running `beetkeeper`.
    ],
)
# `skip_tests=True` keeps Pants' own pytest from running these targets under `pants test`; testing
# is handled exclusively by the `//:pytest` `test_shell_command` (uv-managed pytest). NOTE: the
# `[pytest].skip` subsystem option does NOT do this — it is not consulted by the test goal; only
# this per-target field is. Applies recursively to `python_tests` in subdirectories.
__defaults__({python_tests: dict(dependencies=["//src/release_tests:release-test-utils"], skip_tests=True)})
python_tests()
