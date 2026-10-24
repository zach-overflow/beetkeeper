resource(name="pytyped-marker", source="py.typed")
# Same pattern as provides/beetkeeper-core/src/beetkeeper: git-derived version module, consumed by `_version.py`.
vcs_version(
    name="scm-version",
    generate_to="provides/plugin/src/beetsplug/beetkeeper_plugin/_scm_version.py",
    template='version = "{version}"',
)
python_sources(
    description="The namespaced package for `beetsplug.beetkeeper_plugin` source.",
    dependencies=[
        ":scm-version",
        ":pytyped-marker",
        "//provides/plugin:plugin-requirements",
        "!//provides/beetkeeper-core:app-requirements",
    ],
)
