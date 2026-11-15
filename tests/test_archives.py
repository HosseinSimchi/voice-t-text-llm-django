import pytest

from apps.core.exceptions import ArchiveValidationError
from apps.uploads.archives import Limits, inspect_archive, is_unsafe_member_name, iter_extract
from apps.uploads.sniffing import audio_matches_extension, sniff_archive
from tests.builders import rar_bytes, wav_bytes, zip_bytes


@pytest.fixture
def limits(cfg):
    return Limits.from_config(cfg.uploads)


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_zip_extraction_uses_server_generated_names(tmp_path, limits):
    archive = _write(tmp_path, "a.zip", zip_bytes({"جلسه اول.wav": wav_bytes(), "dir/b.wav": wav_bytes()}))
    out = list(iter_extract(archive, "zip", tmp_path / "out", limits))
    assert [o.reject_reason for o in out] == ["", ""]
    assert {o.path.name for o in out} == {"0000.wav", "0001.wav"}
    assert out[0].display_name == "جلسه اول.wav"
    assert all(o.path.parent == tmp_path / "out" for o in out)


@pytest.mark.parametrize("name", ["../evil.wav", "/etc/passwd.wav", "C:/x.wav", "a/../../b.wav", "..\\x.wav"])
def test_path_traversal_names_are_detected(name):
    assert is_unsafe_member_name(name)


def test_zip_slip_archive_is_rejected(tmp_path, limits):
    archive = _write(tmp_path, "evil.zip", zip_bytes({"ok.wav": wav_bytes(), "../../evil.wav": wav_bytes()}))
    with pytest.raises(ArchiveValidationError) as exc:
        inspect_archive(archive, "zip", limits)
    assert exc.value.code == "archive_path_traversal"
    assert not (tmp_path.parent / "evil.wav").exists()


def test_unsupported_entries_are_reported_not_fatal(tmp_path, limits):
    archive = _write(tmp_path, "mix.zip", zip_bytes({
        "a.wav": wav_bytes(), "notes.txt": b"hello", "inner.zip": b"PK\x03\x04", "fake.mp3": b"not audio at all",
    }, symlinks={"link.wav": "/etc/passwd"}))
    results = {o.display_name: o.reject_reason for o in iter_extract(archive, "zip", tmp_path / "o", limits)}
    assert results["a.wav"] == ""
    assert results["notes.txt"] == "unsupported_file_type"
    assert results["inner.zip"] == "nested_archive_not_supported"
    assert results["fake.mp3"] == "content_does_not_match_extension"
    assert results["link.wav"] == "symbolic_link_not_allowed"


def test_archive_without_audio_is_rejected(tmp_path, limits):
    archive = _write(tmp_path, "x.zip", zip_bytes({"readme.txt": b"x"}))
    with pytest.raises(ArchiveValidationError, match="supported audio"):
        inspect_archive(archive, "zip", limits)


def test_compression_bomb_ratio_is_rejected(tmp_path, limits):
    archive = _write(tmp_path, "bomb.zip", zip_bytes({"bomb.wav": b"\0" * (20 * 1024 * 1024)}))
    with pytest.raises(ArchiveValidationError) as exc:
        inspect_archive(archive, "zip", limits)
    assert exc.value.code == "archive_compression_ratio"


def test_streaming_limits_are_enforced_regardless_of_headers(tmp_path, limits):
    limits.max_file_bytes = 10_000_000
    limits.max_extracted_bytes = 40_000  # smaller than the two files together
    archive = _write(tmp_path, "big.zip", zip_bytes({"a.wav": wav_bytes(1.0), "b.wav": wav_bytes(1.0)}))
    out = list(iter_extract(archive, "zip", tmp_path / "o", limits))
    assert out[0].reject_reason == ""
    assert out[1].reject_reason == "extraction_size_limit_reached"
    assert not (tmp_path / "o" / "0001.wav").exists()


def test_corrupt_zip_is_rejected(tmp_path, limits):
    archive = _write(tmp_path, "c.zip", b"PK\x03\x04" + b"garbage" * 50)
    with pytest.raises(ArchiveValidationError):
        inspect_archive(archive, "zip", limits)


def test_too_many_files(tmp_path, limits):
    limits.max_files = 2
    archive = _write(tmp_path, "m.zip", zip_bytes({f"{i}.wav": wav_bytes(0.1) for i in range(3)}))
    with pytest.raises(ArchiveValidationError) as exc:
        inspect_archive(archive, "zip", limits)
    assert exc.value.code == "too_many_files"


def test_rar_stored_extraction(tmp_path, limits):
    data = rar_bytes({"one.wav": wav_bytes(0.5), "two.txt": b"text"})
    assert sniff_archive(data[:16]) == "rar"
    archive = _write(tmp_path, "a.rar", data)
    entries = inspect_archive(archive, "rar", limits)
    assert [e.display_name for e in entries] == ["one.wav", "two.txt"]
    out = list(iter_extract(archive, "rar", tmp_path / "o", limits))
    assert out[0].reject_reason == "" and out[0].path.read_bytes() == wav_bytes(0.5)
    assert out[1].reject_reason == "unsupported_file_type"


def test_rar_traversal_is_rejected(tmp_path, limits):
    archive = _write(tmp_path, "evil.rar", rar_bytes({"../evil.wav": wav_bytes(0.2)}))
    with pytest.raises(ArchiveValidationError):
        inspect_archive(archive, "rar", limits)


@pytest.mark.parametrize("header,ext,ok", [
    (b"ID3\x04\x00\x00\x00\x00\x00\x00\x00\x00", "mp3", True),
    (b"RIFF\x00\x00\x00\x00WAVEfmt ", "wav", True),
    (b"fLaC\x00\x00\x00\x22" + b"\0" * 4, "flac", True),
    (b"OggS\x00\x02" + b"\0" * 6, "opus", True),
    (b"\x00\x00\x00\x20ftypM4A ", "m4a", True),
    (b"\xff\xf1\x50\x80\x00\x1f\xfc" + b"\0" * 5, "aac", True),
    (b"RIFF\x00\x00\x00\x00WAVEfmt ", "mp3", False),
    (b"<html><body>", "wav", False),
])
def test_audio_magic_detection(header, ext, ok):
    assert audio_matches_extension(header, ext) is ok
