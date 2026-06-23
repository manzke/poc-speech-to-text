"""Unit tests for `server.config` — the wlk argument builder.

These run without a GPU, the model, or WhisperLiveKit installed (NFR-9 dev
parity: the flag logic is pure).
"""

from __future__ import annotations

import pytest

from server import config


def _args(env: dict[str, str]) -> list[str]:
    return config.build_args(env)


def _pairs(args: list[str]) -> dict[str, str]:
    """Collapse a flat ``--flag value`` list into a dict for assertions.

    Boolean flags (no value) map to "" so presence is still testable.
    """
    out: dict[str, str] = {}
    i = 0
    while i < len(args):
        token = args[i]
        if token.startswith("--"):
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                out[token] = args[i + 1]
                i += 2
            else:
                out[token] = ""
                i += 1
        else:
            i += 1
    return out


def test_defaults_are_german_dictation_faster_whisper():
    p = _pairs(_args({}))
    assert p["--backend"] == "faster-whisper"
    assert p["--backend-policy"] == "simulstreaming"
    assert p["--language"] == "de"
    assert p["--model-path"] == config.DEFAULT_MODEL_PATH
    assert "--pcm-input" in p  # ADR-006
    assert p["--beams"] == "1"  # greedy, snappy dictation
    assert p["--frame-threshold"] == "25"
    assert p["--host"] == "0.0.0.0"
    assert p["--port"] == "8000"


def test_subtitles_mode_lowers_frame_threshold():
    p = _pairs(_args({"STT_MODE": "subtitles"}))
    assert p["--frame-threshold"] == "20"
    assert p["--backend-policy"] == "simulstreaming"


def test_language_override():
    p = _pairs(_args({"STT_LANGUAGE": "en"}))
    assert p["--language"] == "en"


def test_model_path_and_warmup_override():
    p = _pairs(_args({"STT_MODEL_PATH": "/models/fallback", "STT_WARMUP_FILE": "/w.wav"}))
    assert p["--model-path"] == "/models/fallback"
    assert p["--warmup-file"] == "/w.wav"


def test_explicit_frame_threshold_and_beams_win():
    p = _pairs(_args({"STT_FRAME_THRESHOLD": "40", "STT_BEAMS": "5"}))
    assert p["--frame-threshold"] == "40"
    assert p["--beams"] == "5"


def test_forwarded_allow_ips_only_when_set():
    assert "--forwarded-allow-ips" not in _pairs(_args({}))
    p = _pairs(_args({"STT_FORWARDED_ALLOW_IPS": "10.0.0.0/8"}))
    assert p["--forwarded-allow-ips"] == "10.0.0.0/8"


def test_extra_args_are_appended_and_split():
    args = _args({"STT_EXTRA_ARGS": "--confidence-validation --min-chunk-size 0.2"})
    assert "--confidence-validation" in args
    assert "--min-chunk-size" in args and "0.2" in args


def test_no_translation_or_diarization_flags_ever_emitted():
    # ADR-008 / ADR-010: these must never appear in the default build.
    args = _args({"STT_MODE": "subtitles", "STT_LANGUAGE": "fr"})
    for forbidden in ("--target-language", "--direct-english-translation", "--diarization"):
        assert forbidden not in args


@pytest.mark.parametrize(
    "device,expected",
    [("cuda", "float16"), ("cpu", "int8")],
)
def test_compute_type_follows_device(device, expected):
    assert config.resolve_compute_type(device, {}) == expected


def test_compute_type_override():
    assert config.resolve_compute_type("cpu", {"STT_COMPUTE_TYPE": "int8_float16"}) == "int8_float16"


def test_invalid_mode_and_device_raise():
    with pytest.raises(ValueError):
        _args({"STT_MODE": "translate"})
    with pytest.raises(ValueError):
        _args({"STT_DEVICE": "tpu"})


def test_render_command_includes_program_name():
    cmd = config.render_command({})
    assert cmd[0] == "wlk"
    assert "--backend" in cmd
