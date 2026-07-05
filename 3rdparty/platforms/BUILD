# https://www.pantsbuild.org/stable/reference/targets/pex_binary#complete_platforms
# https://www.pantsbuild.org/stable/docs/python/overview/pex#generating-the-complete_platforms-file
# https://www.pantsbuild.org/stable/reference/subsystems/python#resolves_to_complete_platforms
# https://packaging.python.org/en/latest/specifications/dependency-specifiers/#defined-environment-marker-fields
# Most, if not all of these JSON files are subsets copied from the pex release below:
# https://github.com/pex-tool/pex/tree/v2.97.1/package/complete-platforms

file(name="linux-aarch64",source="linux-aarch64.json")
file(name="linux-amd64", source="linux-amd64.json")
file(name="macos-aarch64", source="macos-aarch64.json")
file(name="macos-amd64", source="macos-amd64.json")
file(name="musl-aarch64", source="musl-linux-aarch64.json")
file(name="musl-amd64", source="musl-linux-amd64.json")
target(
    name="platforms",
    dependencies=[
        ":linux-aarch64",
        ":linux-amd64", 
        ":macos-aarch64",
        ":macos-amd64",
        ":musl-aarch64",
        ":musl-amd64",
    ],
    tags=["complete-platforms"],
)
