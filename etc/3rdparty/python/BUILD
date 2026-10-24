# `ruamel.yaml`'s dist name != its import root, so map it.
python_requirements(
    name="test-requirements",
    source="test-requirements.txt",
    resolve="beetkeeper-resolve",
    module_mapping={"ruamel.yaml": ["ruamel", "ruamel.yaml"]},
)
python_requirements(name="client-test-requirements", source="client-test-requirements.txt", resolve="client-resolve")
