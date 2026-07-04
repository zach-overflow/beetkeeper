resource(name="alembic-ini", source="alembic.ini")
# The alembic env/revision scripts, `aiosqlite`, and `greenlet` are all loaded dynamically (never imported),
# so inference can't see them; declared here they reach every DB-touching consumer transitively.
python_sources(
    dependencies=[
        ":alembic-ini",
        "./alembic:alembic",
        "./alembic/versions:versions",
        "//src/python:app-requirements#aiosqlite",
        "//src/python:app-requirements#greenlet",
    ]
)
