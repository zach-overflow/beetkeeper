resource(name="pytyped-marker", source="py.typed")
# Same pattern as src/python/beetkeeper: git-derived version module, consumed by `_version.py`.
vcs_version(
    name="scm-version", generate_to="src/beetsplug/beetkeeper_plugin/_scm_version.py", template='version = "{version}"'
)
python_sources(
    description="The namespaced package for `beetsplug.beetkeeper_plugin` source.",
    dependencies=[
        ":scm-version",
        ":pytyped-marker",
        "//src/beetsplug:plugin-requirements",
        "!//src/python:app-requirements",
    ],
)
