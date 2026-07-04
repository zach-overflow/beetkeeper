python_test_utils(
    name="release-test-utils",
    dependencies=[
        "//src/beetsplug:plugin-pyproject",
        "//src/python/beetkeeper:beetkeeper",
        "//src/python:app-requirements",
    ],
)
# skip_tests=True: `[pytest].skip` is a no-op for the test goal, so only this per-target field keeps
# Pants' own pytest off these; we test via `//:pytest`. Applies recursively to subdirectories.
__defaults__(
    {python_tests: dict(dependencies=["//src/integration_tests/release_tests:release-test-utils"], skip_tests=True)},
    extend=True,
)
python_tests()
