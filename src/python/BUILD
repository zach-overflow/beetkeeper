file(name="pypi-readme", source="README.md")
# With `generate_setup=False`, setuptools reads this pyproject directly (version via setuptools-scm).
file(name="dist-pyproject", source="pyproject.toml")
python_requirements(name="app-requirements", source="pyproject.toml")
# `files` hack pending https://github.com/pantsbuild/pants/issues/18379
files(
    name="lib-source-files",
    description="All files in `src/python/beetkeeper. Only use this in the app Docker image.",
    sources=[
        "./beetkeeper/**/*.py",
        "beetkeeper/**/py.typed",
        "./beetkeeper/**/*.ini",
        "./beetkeeper/**/*.mako",
        "./beetkeeper/**/*.html",
        "./beetkeeper/**/*.css",
        "./beetkeeper/**/*.js",
        "!./tests/**/*.pyi",
    ],
)

python_distribution(
    name="beetkeeper-whl",
    # Alembic env/version scripts are loaded dynamically, so inference can't see them; list them explicitly.
    dependencies=[
        ":dist-pyproject",
        ":pypi-readme",
        "./beetkeeper:beetkeeper",
        "./beetkeeper:scm-version",
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
