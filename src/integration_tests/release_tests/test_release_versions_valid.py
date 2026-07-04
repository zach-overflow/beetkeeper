"""Various tests to ensure there's no accidental drift in semver values, either statically defined, or set via git tags on a pending release run."""

import pytest


def test_static_file_base_versions_match(
    canonical_semver: str, beetkeeper_plugin_semver: str, beetkeeper_server_semver: str
) -> None:
    """
    Ensures both distributions' committed versions equal the canonical `VERSION` (and thus each other).
    """
    assert beetkeeper_server_semver == canonical_semver, (
        f"`src/python/beetkeeper/_version.py` ('{beetkeeper_server_semver}') != VERSION ('{canonical_semver}'); run hooks/version-sync.sh"
    )
    assert beetkeeper_plugin_semver == canonical_semver, (
        f"`src/beetsplug/pyproject.toml` ('{beetkeeper_plugin_semver}') != VERSION ('{canonical_semver}'); run hooks/version-sync.sh"
    )


def test_git_tag_matches_static_versions(github_release_tag_semver: str | None, canonical_semver: str) -> None:
    """
    Ensures the latest semver tag corresponding to the current GitHub Action run matches that of the statically
    defined versions in `src/beetsplug/pyproject.toml` and `src/python/beetkeeper/_version.py`.
    Skips if run outside of a GitHub Actions environment, or is running from a non-tag-based workflow in GH Actions.
    """
    if github_release_tag_semver is None:
        pytest.skip(reason="No release tag to validate (not a `vMAJOR.MINOR.PATCH` tag-triggered GitHub Actions run).")
    # `test_static_file_base_versions_match` already ties both files to the canonical `VERSION`, so validating the
    # tag against the canonical is sufficient to cover all three.
    assert github_release_tag_semver == canonical_semver, (
        f"Release tag 'v{github_release_tag_semver}' != VERSION ('{canonical_semver}'); bump VERSION + run hooks/version-sync.sh before tagging."
    )
