file(name="test-container-config", source="test_beets_conf.yaml")
shell_sources(dependencies=[":test-container-config"])
python_source(
    name="prep-fake-audio-files",
    source="./prep_fake_audio_files.py",
    # mutagen is only a transitive dep (via beets), so `import mutagen.flac` can't be inferred; depending on
    # beets makes subset runs (e.g. `pants check build_scripts::`) work, matching the PEX it runs inside.
    dependencies=["./fake_tag_data:fake_tag_data", "src/python:app-requirements#beets", ":test-container-config"],
)
