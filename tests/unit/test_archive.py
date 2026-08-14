from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from acoustic_ladder.model_package.archive import (
    ArchiveSafetyError,
    MissingRequiredEntryError,
    PackageParseError,
    classify_entry,
    decode_text,
    inspect_archive,
    read_csv,
    read_json,
    sha256_file,
)


def _zip(path: Path, entries: list[tuple[str, bytes]]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return path


def test_sha256_file(tmp_path: Path) -> None:
    path = tmp_path / "payload.bin"
    path.write_bytes(b"acoustic-ladder")
    assert sha256_file(path) == hashlib.sha256(b"acoustic-ladder").hexdigest()


@pytest.mark.parametrize(
    ("path", "category"),
    [
        ("root/stl/batch/part.stl", "stl"),
        ("root/step/part.step", "part_step"),
        ("root/assemblies/device.step", "assembly_step"),
        ("root/source/v1_params.py", "python_source"),
        ("root/reports/data.json", "json_report"),
        ("root/reports/data.csv", "csv_report"),
    ],
)
def test_classify_entry(path: str, category: str) -> None:
    assert classify_entry(path) == category


def test_utf8_sig_csv(tmp_path: Path) -> None:
    package = _zip(tmp_path / "csv.zip", [("root/reports/data.csv", b"\xef\xbb\xbfa,b\n1,2\n")])
    with zipfile.ZipFile(package) as archive:
        assert read_csv(archive, "reports/data.csv") == [{"a": "1", "b": "2"}]


def test_json_parsing(tmp_path: Path) -> None:
    package = _zip(tmp_path / "json.zip", [("root/reports/data.json", b'{"version":"V1.3"}')])
    with zipfile.ZipFile(package) as archive:
        assert read_json(archive, "reports/data.json") == {"version": "V1.3"}


def test_utf8_sig_decoder() -> None:
    assert decode_text(b"\xef\xbb\xbfhello") == "hello"


def test_missing_required_entry(tmp_path: Path) -> None:
    package = _zip(tmp_path / "missing.zip", [("root/README.txt", b"not enough")])
    with pytest.raises(MissingRequiredEntryError):
        inspect_archive(package)


def test_corrupt_json(tmp_path: Path) -> None:
    package = _zip(tmp_path / "bad-json.zip", [("root/reports/data.json", b"{")])
    with zipfile.ZipFile(package) as archive, pytest.raises(PackageParseError):
        read_json(archive, "reports/data.json")


def test_corrupt_csv(tmp_path: Path) -> None:
    package = _zip(tmp_path / "bad-csv.zip", [("root/reports/data.csv", b'a,b\n"unterminated')])
    with zipfile.ZipFile(package) as archive, pytest.raises(PackageParseError):
        read_csv(archive, "reports/data.csv")


@pytest.mark.parametrize("unsafe_name", ["root/../evil.txt", "/absolute.txt", "C:\\absolute.txt"])
def test_unsafe_archive_paths(tmp_path: Path, unsafe_name: str) -> None:
    package = _zip(tmp_path / "unsafe.zip", [(unsafe_name, b"unsafe")])
    with pytest.raises(ArchiveSafetyError):
        inspect_archive(package)


def test_duplicate_normalized_archive_path(tmp_path: Path) -> None:
    package = _zip(
        tmp_path / "duplicate.zip",
        [("root/reports/value.txt", b"one"), ("root/reports/./value.txt", b"two")],
    )
    with pytest.raises(ArchiveSafetyError):
        inspect_archive(package)
