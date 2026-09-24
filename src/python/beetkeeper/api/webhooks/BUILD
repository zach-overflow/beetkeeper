# Since the `webhooks` module should only contain auto-doc generation, directly attached to the FastAPI app instance,
# we lock down the allowed dependency pathways with `__dependencies_rules__`: anything in this directory tree may
# depend only on this tree and on third-party requirements — never on the rest of the app.
# See also: https://www.pantsbuild.org/stable/docs/using-pants/validating-dependencies
__dependencies_rules__(
    # Pants infers a dependency on every ancestor package `__init__.py`, so those two are allowed explicitly.
    (
        "*",
        "/**",
        "<python_requirements>",
        "//src/python/beetkeeper/__init__.py",
        "//src/python/beetkeeper/api/__init__.py",
        "!*",
    )
)

python_sources()
