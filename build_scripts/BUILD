shell_sources()
run_shell_command(
    name="run-test-server",
    command="./build_scripts/run-test-server.sh",
    workdir="/",
    execution_dependencies=["build_scripts/run-test-server.sh", "//:beetkeeper-server-image"],
)


python_source(name="openapi-spec-exporter-script", source="export_openapi.py", resolve="beetkeeper-resolve")
pex_binary(
    name="openapi-json-exporter",
    entry_point="export_openapi.py",
    resolve="beetkeeper-resolve",
    dependencies=[":openapi-spec-exporter-script", "//src/python:app-requirements"],
)
