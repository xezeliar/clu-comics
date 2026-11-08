"""The fork's version label keeps the author's version and the update check intact."""
import pathlib

from packaging import version as pkg_version

from core import version

ROOT = pathlib.Path(__file__).resolve().parents[2]


def test_version_is_upstream_plus_fork_label():
    assert version.__version__ == f"{version.UPSTREAM_VERSION}+{version.FORK_LABEL}"


def test_label_is_a_valid_local_version():
    parsed = pkg_version.parse(version.__version__)
    assert parsed.public == version.UPSTREAM_VERSION
    assert parsed.local == version.FORK_LABEL


def test_upstreams_next_release_still_counts_as_an_update():
    upstream = pkg_version.parse(version.UPSTREAM_VERSION)
    ours = pkg_version.parse(version.__version__)
    next_release = pkg_version.parse(f"{upstream.major}.{upstream.minor + 1}")
    assert next_release > ours


def test_the_same_upstream_release_is_not_reported_as_an_update():
    assert not pkg_version.parse(version.UPSTREAM_VERSION) > pkg_version.parse(version.__version__)


def test_providers_see_the_plain_upstream_version():
    assert version.CLU_USER_AGENT == f"CLU/{version.UPSTREAM_VERSION}"


def test_upstream_version_line_is_left_as_upstream_writes_it():
    """Their release bumps edit this line; keeping it untouched keeps merges clean."""
    src = (ROOT / "core" / "version.py").read_text(encoding="utf-8")
    first = next(line for line in src.splitlines() if line.startswith("__version__ = "))
    assert first == f'__version__ = "{version.UPSTREAM_VERSION}"'
