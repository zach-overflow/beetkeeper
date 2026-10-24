python_test_utils(
    name="meta-test-utils",
    dependencies=[
        "//provides/beetkeeper-core:dist-pyproject",
        "//provides/plugin:plugin-pyproject",
        "//etc/3rdparty/tools:tools-resolve-requirements-file",
        # `test_wheel_static_assets.py` enumerates these on disk to check package-data coverage.
        "//provides/beetkeeper-core/src/beetkeeper/api/static:static-app-files",
    ],
)

# These tests read repo source files directly, so declare them as deps to materialize them into the
# sandbox. Overriding `dependencies` also replaces the parent `__defaults__`, which these tests don't need.
python_tests(dependencies=[":meta-test-utils"])
