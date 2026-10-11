# Pants generates `beetkeeper_api_client` into this source root at build time (never written to the repo).
# `client-resolve` must hold every runtime dep the generator declares, or codegen fails.
openapi_document(
    name="openapi-spec",
    source="openapi.json",
    python_generator_name="python",
    python_resolve="client-resolve",
    # https://openapi-generator.tech/docs/generators/python#config-options
    python_additional_properties={
        "packageName": "beetkeeper_api_client",
        # Only sets the generated `__version__` and default User-Agent; the wheel version is `:scm-version`.
        "packageVersion": env("RELEASE_TAG", "0.0.0.dev0"),
        "library": "httpx2",
        "supportHttpxSync": "true",
    },
)
# Pants keeps only the generator's `*.py` output, so the marker is committed.
resource(name="py-typed", source="beetkeeper_api_client/py.typed")
# Same pattern as beetkeeper-core/src/beetkeeper: git-derived version module, read by setuptools at build time.
vcs_version(
    name="scm-version", generate_to="client/src/beetkeeper_api_client/_scm_version.py", template='version = "{version}"'
)
