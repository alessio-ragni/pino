"""One version for the whole project: server package, pyproject, Android app."""

import re
from pathlib import Path

from pino import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_versions_agree():
    pyproject = (ROOT / "server" / "pyproject.toml").read_text()
    assert re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1) == __version__
    gradle = (ROOT / "android" / "app" / "build.gradle.kts").read_text()
    name = re.search(r'versionName = "([^"]+)"', gradle).group(1)
    code = int(re.search(r"versionCode = (\d+)", gradle).group(1))
    major, minor, patch = (int(x) for x in __version__.split("."))
    assert name == __version__
    assert code == major * 10000 + minor * 100 + patch


def test_changelog_has_this_version():
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert f"## [{__version__}]" in changelog or "## [Unreleased]" in changelog
