file(name="pypi-readme", source="README.md")
# With `generate_setup=False`, setuptools reads this pyproject directly (version via setuptools-scm).
file(name="dist-pyproject", source="pyproject.toml")
python_requirements(name="app-requirements", source="pyproject.toml")
# `files` hack pending https://github.com/pantsbuild/pants/issues/18379
files(
    name="lib-source-files",
    description="All files in `beetkeeper-core/src/beetkeeper`. Only use this in the app Docker image.",
    sources=[
        "./src/beetkeeper/**/*.py",
        "./src/beetkeeper/**/py.typed",
        "./src/beetkeeper/**/*.ini",
        "./src/beetkeeper/**/*.mako",
        "./src/beetkeeper/**/*.html",
        "./src/beetkeeper/**/*.css",
        "./src/beetkeeper/**/*.js",
        "!./src/tests/**/*.pyi",
    ],
)

python_distribution(
    name="beetkeeper-whl",
    # Alembic env/version scripts are loaded dynamically, so inference can't see them; list them explicitly.
    dependencies=[
        ":dist-pyproject",
        ":pypi-readme",
        "./src/beetkeeper:beetkeeper",
        "./src/beetkeeper:scm-version",
        "./src/beetkeeper/db:alembic-ini",
        "./src/beetkeeper/db/alembic",
        "./src/beetkeeper/db/alembic:script-mako",
        "./src/beetkeeper/db/alembic/versions",
    ],
    provides=python_artifact(name="beetkeeper"),
    sdist=False,
    wheel=True,
    generate_setup=False,
)
