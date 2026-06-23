#!/usr/bin/env python3
"""CI license gate (NFR-7 / ADR-009).

Runs `pip-licenses` over the installed dependency tree and fails if any shipped
third-party package is under a non-permissive license, unless it appears on the
explicit allowlist below. This enforces the "strict permissive by default"
posture for the components we REDISTRIBUTE — it does not police this repo's own
AGPL-3.0 license.

Policy (owner decisions):
  * Permissive (MIT/BSD/Apache/PSF/ISC/MPL-2.0/…) -> allowed.
  * Weak/lib-level copyleft (LGPL) -> allowed: dynamically linked, imposes no
    copyleft on our code (e.g. `soxr`, a transitive `librosa` dep).
  * Strong/network copyleft (GPL/AGPL/SSPL) and non-commercial/CC -> blocked.
  * NVIDIA CUDA runtime wheels (GPU variant) -> allowed by prefix under the
    NVIDIA CUDA EULA (accepted in the PRD licensing matrix).
  * Translation/diarization packages -> hard-blocked regardless of license.

Usage:  pip install pip-licenses && python scripts/check_licenses.py
"""

from __future__ import annotations

import json
import subprocess
import sys

# License substrings considered permissive and safe to redistribute.
PERMISSIVE = (
    "MIT",
    "BSD",
    "APACHE",
    "PSF",
    "PYTHON SOFTWARE FOUNDATION",
    "ISC",
    "HISTORICAL PERMISSION NOTICE",  # HPND
    "ZLIB",
    "MOZILLA PUBLIC LICENSE 2.0",  # MPL-2.0: weak-copyleft, file-level; acceptable
    "MPL-2.0",
    "UNLICENSE",
    "0BSD",
    "WTFPL",
)

# Weak (lib-level) copyleft we explicitly accept (per owner decision): LGPL
# imposes no copyleft on our own code when the library is dynamically linked, as
# is the case for our transitive deps (e.g. `soxr`, pulled by `librosa`). Strong
# copyleft (GPL/AGPL/SSPL) and non-commercial/CC remain hard violations below.
WEAK_COPYLEFT_ALLOWED = (
    "LGPL",
    "LESSER GENERAL PUBLIC",
)

# Always-block tokens: strong/network copyleft and non-commercial/Creative
# Commons. Checked BEFORE the permissive/weak-copyleft tokens so an "AGPL" or
# "CC-BY-NC" string can never be waved through.
HARD_BLOCK = (
    "AGPL",
    "AFFERO",
    "SSPL",
    "NON-COMMERCIAL",
    "NONCOMMERCIAL",
    "CC-BY-NC",
    "CREATIVE COMMONS",
)

# Per-package exceptions: packages whose metadata license is missing/ambiguous
# but whose actual license is known-good. Keep this list short and justified.
PACKAGE_ALLOWLIST = {
    # openai/triton — MIT, but metadata is often blank.
    "triton",
    # setuptools — MIT/PSF, frequently reported as UNKNOWN by pip metadata.
    "setuptools",
}

# Packages that, if present, indicate a forbidden extra leaked into the build
# (ADR-008 translation / ADR-010 diarization). Their presence is a hard failure
# regardless of license.
FORBIDDEN_PACKAGES = {
    "pyannote.audio",  # gated diarization models (ADR-010)
    "nemo-toolkit",    # Sortformer diarization, deferred (ADR-010)
}


def is_nvidia_cuda(name: str) -> bool:
    """NVIDIA CUDA runtime wheels (any CUDA major: -cu12/-cu13/...).

    Pulled in by the CUDA build of torch/ctranslate2. Redistributable under the
    NVIDIA CUDA EULA and already accepted in the PRD licensing matrix for the GPU
    variant; their pip metadata is NVIDIA-proprietary, so allow them by prefix.
    """
    low = name.lower()
    return low.startswith(("nvidia-", "nvidia_", "cuda-", "cuda_"))


def is_permissive(license_str: str) -> bool:
    up = (license_str or "").upper()
    return any(token in up for token in PERMISSIVE)


def is_acceptable_license(license_str: str) -> bool:
    """Classify a license string: True = redistributable under our policy.

    Order matters: hard blocks first, then weak-copyleft allow, then plain GPL
    block, then the permissive allowlist.
    """
    up = (license_str or "").upper()
    if any(tok in up for tok in HARD_BLOCK):
        return False
    if any(tok in up for tok in WEAK_COPYLEFT_ALLOWED):
        return True
    if "GENERAL PUBLIC LICENSE" in up or "GPL" in up:  # plain GPL = strong copyleft
        return False
    return is_permissive(up)


def main() -> int:
    raw = subprocess.check_output(
        ["pip-licenses", "--format=json", "--with-system"], text=True
    )
    packages = json.loads(raw)

    violations: list[str] = []
    forbidden: list[str] = []

    for pkg in packages:
        name = pkg.get("Name", "")
        license_str = pkg.get("License", "")
        if name.lower() in {p.lower() for p in FORBIDDEN_PACKAGES}:
            forbidden.append(f"{name} ({license_str})")
            continue
        if name in PACKAGE_ALLOWLIST or is_nvidia_cuda(name):
            continue
        if not is_acceptable_license(license_str):
            violations.append(f"{name}: {license_str!r}")

    ok = True
    if forbidden:
        ok = False
        print("FORBIDDEN packages present (translation/diarization must not ship):")
        for f in forbidden:
            print(f"  - {f}")

    if violations:
        ok = False
        print("Non-permissive dependency licenses (NFR-7 / ADR-009 violation):")
        for v in violations:
            print(f"  - {v}")
        print(
            "\nIf a license string is merely missing/mislabeled but is actually "
            "permissive (or weak-copyleft LGPL), add the package to "
            "PACKAGE_ALLOWLIST with a comment, or extend the policy tokens."
        )

    if ok:
        print(f"License gate passed: {len(packages)} packages, all acceptable.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
