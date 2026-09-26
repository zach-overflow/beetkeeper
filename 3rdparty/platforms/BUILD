# Pex "complete platform" JSONs consumed by the root BUILD's `app_server_pexes` targets (the linux pair also feeds
# the image). Generated only by `build_scripts/generate-complete-platforms.sh`, never hand-edited; see
# docs/contributor_docs/building_artifacts.md#regenerating-the-complete-platform-jsons

file(name="linux-arm64", source="linux-arm64.json")
file(name="linux-amd64", source="linux-amd64.json")
file(name="macos-arm64", source="macos-arm64.json")
file(name="macos-amd64", source="macos-amd64.json")
target(
    name="platforms",
    dependencies=[":linux-arm64", ":linux-amd64", ":macos-arm64", ":macos-amd64"],
    tags=["complete-platforms"],
)
