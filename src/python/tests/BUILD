python_test_utils(
    name="base-pytest-utils", dependencies=["//src/python/beetkeeper:beetkeeper", "//src/python:app-requirements"]
)
__defaults__(
    {
        (python_tests, python_test_utils): dict(
            dependencies=["//src/python/tests:base-pytest-utils", "//src/python:app-requirements"]
        )
    },
    extend=True,
)
python_tests()
