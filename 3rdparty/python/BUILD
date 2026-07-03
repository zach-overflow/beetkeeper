# Test-only third-party requirements for the `beetkeeper-resolve` (test code's resolve). Lets `pants check`
# (mypy) resolve test imports like `pytest`/`httpx` without these landing in any published wheel. See the
# header comment in `test-requirements.txt`. `ruamel.yaml`'s dist name != its import root, so map it.
python_requirements(
    name="test-requirements",
    source="test-requirements.txt",
    resolve="beetkeeper-resolve",
    module_mapping={"ruamel.yaml": ["ruamel", "ruamel.yaml"]},
)
