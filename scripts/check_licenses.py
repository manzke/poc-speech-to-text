#!/usr/bin/env python3
"""CI license gate (NFR-7 / ADR-009).

Runs `pip-licenses` over the installed dependency tree and fails if any shipped
third-party package is under a non-permissive license, unless it appears on the
explicit allowlist below. This enforces the "strict permissive by default"
posture for the components we REDISTRIBUTE — it does not police this repo's own
AGPL-3.0 license.

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
    "UNLICENSE",
    "0BSD",
    "WTFPL",
)

# Per-package exceptions: packages whose metadata license is missing/ambiguous
# but whose actual license is known-good. Keep this list short and justified.
PACKAGE_ALLOWLIST = {
    # NVIDIA CUDA runtime wheels pulled in by the CUDA (cu129) build. Shipped
    # under the NVIDIA CUDA EULA, which permits redistribution of the runtime;
    # they are NOT present in the CPU build scanned by CI but are allowlisted so
    # the same gate passes if ever run against the GPU image.
    "nvidia-cublas-cu12", "nvidia-cuda-cupti-cu12", "nvidia-cuda-nvrtc-cu12",
    "nvidia-cuda-runtime-cu12", "nvidia-cudnn-cu12", "nvidia-cufft-cu12",
    "nvidia-curand-cu12", "nvidia-cusolver-cu12", "nvidia-cusparse-cu12",
    "nvidia-nccl-cu12", "nvidia-nvjitlink-cu12", "nvidia-nvtx-cu12",
    "triton",
}

# Packages that, if present, indicate a forbidden extra leaked into the build
# (ADR-008 translation / ADR-010 diarization). Their presence is a hard failure
# regardless of license.
FORBIDDEN_PACKAGES = {
    "pyannote.audio",  # gated diarization models (ADR-010)
    "nemo-toolkit",    # Sortformer diarization, deferred (ADR-010)
}


def is_permissive(license_str: str) -> bool:
    up = (license_str or "").upper()
    return any(token in up for token in PERMISSIVE)


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
        if name in PACKAGE_ALLOWLIST:
            continue
        if not is_permissive(license_str):
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
            "Apache/MIT/BSD, add the package to PACKAGE_ALLOWLIST with a comment."
        )

    if ok:
        print(f"License gate passed: {len(packages)} packages, all permissive.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
