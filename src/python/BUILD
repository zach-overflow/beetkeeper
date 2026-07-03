# Build config for this distribution lives in `src/python/pyproject.toml` (co-located in the
# source root so it lands in the PEP 517 backend's working dir). With `generate_setup=False`,
# setuptools reads that file and resolves the version from `beetkeeper._version.__version__`.
file(name="dist-pyproject", source="pyproject.toml")
python_requirements(name="app-requirements", source="pyproject.toml")
# We have to use this `files` hack until this is fixed in Pantsbuild: https://github.com/pantsbuild/pants/issues/18379
files(
    name="lib-source-files",
    description="All files in `src/python/beetkeeper. Only use this in the app Docker image.",
    sources=[
        "./beetkeeper/**/*.py",
        "beetkeeper/**/py.typed",
        "./beetkeeper/**/*.ini",
        "./beetkeeper/**/*.mako",
        # Frontend assets (templates, CSS, vendored HTMX) served by the UI routes / StaticFiles mount.
        "./beetkeeper/**/*.html",
        "./beetkeeper/**/*.css",
        "./beetkeeper/**/*.js",
        "!./tests/**/*.pyi",
    ],
)

python_distribution(
    name="beetkeeper-whl",
    # The alembic env + version scripts are loaded dynamically (not imported), so dependency inference
    # cannot see them — list them (and the packaged ini/mako resources) explicitly so they land in the wheel.
    dependencies=[
        ":dist-pyproject",
        "./beetkeeper:beetkeeper",
        "./beetkeeper/db:alembic-ini",
        "./beetkeeper/db/alembic",
        "./beetkeeper/db/alembic:script-mako",
        "./beetkeeper/db/alembic/versions",
    ],
    provides=python_artifact(name="beetkeeper"),
    sdist=False,
    wheel=True,
    generate_setup=False,
)
