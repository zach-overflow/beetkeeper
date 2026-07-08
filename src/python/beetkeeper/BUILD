resource(name="pytyped-marker", source="py.typed")
# Computes the version from git state via setuptools-scm (Pants runs it against the real repo, then
# materializes the generated module into consuming sandboxes). See `_version.py` for the consumer.
vcs_version(name="scm-version", generate_to="src/python/beetkeeper/_scm_version.py", template='version = "{version}"')
python_sources(
    description="The root module of beetkeeper source.",
    dependencies=[
        ":scm-version",
        "./api:api",
        "./core:core",
        "./db:db",
        ":pytyped-marker",
        "./settings:settings",
        "./_cli_utils:_cli_utils",
    ],
)
