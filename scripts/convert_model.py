#!/usr/bin/env python3
"""Convert a Hugging Face Whisper model to CTranslate2 format and bake it in.

Run at **image build time** (ADR-005): the converted model is written into the
image so there is zero Hugging Face egress at runtime (FR-6, air-gap). The
faster-whisper backend expects a CTranslate2 directory, which is what
`ct2-transformers-converter` (shipped with `ctranslate2`) produces.

Per-arch quantization (ADR-004 / §9):
    * GPU / amd64 build  -> ``float16``
    * CPU / arm64 build  -> ``int8``

Usage (invoked from the Dockerfile):

    python scripts/convert_model.py \
        --model-id primeline/whisper-large-v3-turbo-german \
        --output /models/de-default \
        --quantization int8

The default model is the Apache-2.0 German turbo fine-tune (ADR-001). Pass
``--model-id openai/whisper-large-v3`` to bake the MIT base fallback instead.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_MODEL_ID = "primeline/whisper-large-v3-turbo-german"
FALLBACK_MODEL_ID = "openai/whisper-large-v3"
VALID_QUANTIZATION = ("int8", "int8_float16", "float16", "float32")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model-id", default=os.environ.get("MODEL_ID", DEFAULT_MODEL_ID))
    p.add_argument("--output", default=os.environ.get("MODEL_OUTPUT", "/models/de-default"))
    p.add_argument(
        "--quantization",
        default=os.environ.get("MODEL_QUANTIZATION", "int8"),
        choices=VALID_QUANTIZATION,
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-convert even if the output directory already looks populated.",
    )
    return p.parse_args(argv)


def already_converted(output: Path) -> bool:
    return (output / "model.bin").exists() and (output / "config.json").exists()


def write_provenance(output: Path, model_id: str, quantization: str) -> None:
    """Drop a small provenance file next to the weights for license clarity (ADR-005)."""
    (output / "MODEL_PROVENANCE.txt").write_text(
        "Converted from Hugging Face model: {model}\n"
        "CTranslate2 quantization: {quant}\n"
        "License: see the source model card (Apache-2.0 for primeline/* defaults,\n"
        "MIT for openai/whisper-* fallback). Re-verify on each version bump.\n".format(
            model=model_id, quant=quantization
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = Path(args.output)

    if already_converted(output) and not args.force:
        print(f"[convert] model already present at {output}, skipping", file=sys.stderr)
        return 0

    output.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ct2-transformers-converter",
        "--model", args.model_id,
        "--output_dir", str(output),
        "--copy_files", "tokenizer.json", "preprocessor_config.json",
        "--quantization", args.quantization,
    ]
    if args.force:
        cmd.append("--force")

    print(f"[convert] {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("[convert] conversion failed", file=sys.stderr)
        return result.returncode

    write_provenance(output, args.model_id, args.quantization)
    print(f"[convert] baked {args.model_id} ({args.quantization}) into {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
