python_test_utils(
    name="base-pytest-utils",
    dependencies=["//beetkeeper-core/src/beetkeeper:beetkeeper", "//beetkeeper-core:app-requirements"],
)
__defaults__(
    {
        (python_tests, python_test_utils): dict(
            dependencies=["//beetkeeper-core/src/tests:base-pytest-utils", "//beetkeeper-core:app-requirements"]
        )
    },
    extend=True,
)
python_tests()
