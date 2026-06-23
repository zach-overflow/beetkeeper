python_test_utils(
    name="plugin-integration-test-utils",
    dependencies=[
        "src/beetsplug/tests",
        "src/beetsplug/beetkeeper_plugin:beetkeeper_plugin",
        "src/python:beetkeeper-whl",
    ],
)
python_tests(name="plugin-integration-tests", dependencies=[":plugin-integration-test-utils"])
