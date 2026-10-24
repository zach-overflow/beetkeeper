shell_sources()
run_shell_command(
    name="run-test-server",
    command="./etc/build_scripts/run-test-server.sh",
    workdir="/",
    execution_dependencies=["etc/build_scripts/run-test-server.sh", "//etc/docker:beetkeeper-server-image"],
)


python_source(name="openapi-spec-exporter-script", source="export_openapi.py", resolve="beetkeeper-resolve")
pex_binary(
    name="openapi-json-exporter",
    entry_point="export_openapi.py",
    resolve="beetkeeper-resolve",
    dependencies=[":openapi-spec-exporter-script", "//provides/beetkeeper-core:app-requirements"],
)
