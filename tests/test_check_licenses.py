"""Unit tests for the CI license-gate classifier (scripts/check_licenses.py)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

# Load scripts/check_licenses.py as a module (it lives outside a package).
_spec = importlib.util.spec_from_file_location(
    "check_licenses",
    Path(__file__).resolve().parent.parent / "scripts" / "check_licenses.py",
)
cl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cl)


@pytest.mark.parametrize(
    "license_str",
    ["MIT", "BSD-3-Clause", "Apache-2.0", "ISC", "MPL-2.0",
     "Python Software Foundation License"],
)
def test_permissive_allowed(license_str):
    assert cl.is_acceptable_license(license_str) is True


def test_lgpl_weak_copyleft_allowed():
    # Owner decision: LGPL (e.g. soxr) is allowed.
    assert cl.is_acceptable_license("LGPL-2.1-or-later") is True
    assert cl.is_acceptable_license("GNU Lesser General Public License v3") is True


@pytest.mark.parametrize(
    "license_str",
    ["GPL-3.0", "GNU General Public License v2", "AGPL-3.0",
     "GNU Affero General Public License", "SSPL-1.0",
     "CC-BY-NC-4.0", "Creative Commons Attribution Non-Commercial"],
)
def test_strong_copyleft_and_noncommercial_blocked(license_str):
    assert cl.is_acceptable_license(license_str) is False


def test_unknown_blocked_unless_allowlisted():
    assert cl.is_acceptable_license("UNKNOWN") is False


def test_nvidia_cuda_prefix_allowed():
    # The exact packages that failed CI (any CUDA major).
    for name in ("nvidia-cublas-cu13", "nvidia-cudnn-cu13", "cuda-bindings",
                 "cuda-toolkit", "cuda-pathfinder"):
        assert cl.is_nvidia_cuda(name) is True
    assert cl.is_nvidia_cuda("librosa") is False


def test_forbidden_packages_listed():
    assert "pyannote.audio" in cl.FORBIDDEN_PACKAGES
    assert "nemo-toolkit" in cl.FORBIDDEN_PACKAGES
