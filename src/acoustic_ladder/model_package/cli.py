"""Command-line interface for DEV-01.01 model-package operations."""

from __future__ import annotations

import argparse
from pathlib import Path

from acoustic_ladder.model_package.archive import EXPECTED_V1_3_SHA256, inspect_archive
from acoustic_ladder.model_package.calibration import (
    canonical_json_bytes,
    load_calibration_record,
    normalize_calibration_record,
)
from acoustic_ladder.model_package.normalize import (
    generate_manifest,
    recompute_sidecar,
    validate_manifest_file,
    verify_sidecar,
    write_manifest,
)


def _parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m acoustic_ladder.model_package",
        description="Safely audit a model package and generate a provisional device manifest.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Audit a ZIP without executing it")
    inspect_parser.add_argument("archive")
    inspect_parser.add_argument("--calibration", required=True)
    inspect_parser.add_argument("--output", required=True)
    inspect_parser.add_argument("--expected-sha256", default=EXPECTED_V1_3_SHA256)

    calibration_parser = subparsers.add_parser(
        "normalize-calibration", help="Validate and canonicalize the user calibration record"
    )
    calibration_parser.add_argument("input")
    calibration_parser.add_argument("--output-json", required=True)
    calibration_parser.add_argument("--output-markdown", required=True)

    generate_parser = subparsers.add_parser(
        "generate", help="Generate a deterministic provisional manifest"
    )
    generate_parser.add_argument("archive")
    generate_parser.add_argument("--calibration", required=True)
    generate_parser.add_argument("--output", required=True)
    generate_parser.add_argument("--sidecar", required=True)
    generate_parser.add_argument("--expected-sha256", default=EXPECTED_V1_3_SHA256)

    validate_parser = subparsers.add_parser(
        "validate", help="Validate a manifest schema and stable SHA256 sidecar"
    )
    validate_parser.add_argument("manifest")
    validate_parser.add_argument("--schema", required=True)
    validate_parser.add_argument("--sidecar", required=True)

    hash_parser = subparsers.add_parser("hash", help="Recompute a manifest SHA256 sidecar")
    hash_parser.add_argument("manifest")
    hash_parser.add_argument("--sidecar", required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Run one CLI operation."""

    args = _parser().parse_args(argv)
    if args.command == "inspect":
        calibration = load_calibration_record(args.calibration)
        audit = inspect_archive(
            args.archive,
            expected_sha256=args.expected_sha256,
            calibration_record=calibration,
        )
        _parent(args.output)
        Path(args.output).write_bytes(canonical_json_bytes(audit))
        print(f"PASS archive audit: {args.output}")
        return
    if args.command == "normalize-calibration":
        _parent(args.output_json)
        _parent(args.output_markdown)
        normalize_calibration_record(args.input, args.output_json, args.output_markdown)
        print(f"PASS calibration normalization: {args.output_json}")
        return
    if args.command == "generate":
        manifest = generate_manifest(
            args.archive,
            args.calibration,
            expected_sha256=args.expected_sha256,
        )
        _parent(args.output)
        _parent(args.sidecar)
        digest = write_manifest(manifest, args.output, args.sidecar)
        print(f"PASS provisional manifest: {args.output} ({digest})")
        return
    if args.command == "validate":
        validate_manifest_file(args.manifest, args.schema)
        digest = verify_sidecar(args.manifest, args.sidecar)
        print(f"PASS manifest validation: {digest}")
        return
    if args.command == "hash":
        _parent(args.sidecar)
        digest = recompute_sidecar(args.manifest, args.sidecar)
        print(f"PASS manifest sidecar: {digest}")
        return
    raise AssertionError(f"Unhandled command {args.command}")
