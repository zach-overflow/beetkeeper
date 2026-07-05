# These tests read repo source files directly, so declare them as deps to materialize them into the
# sandbox. Overriding `dependencies` also replaces the parent `__defaults__`, which these tests don't need.
python_tests(
    dependencies=[
        "//src/python:dist-pyproject",
        "//3rdparty/tools:tools-resolve-requirements-file",
        # `test_wheel_static_assets.py` enumerates these on disk to check package-data coverage.
        "//src/python/beetkeeper/api/static:static-app-files",
    ]
)
