"""tools/check_sdist.py: an sdist must contain every License-File its metadata declares."""

from __future__ import annotations

import importlib.util
import io
import pathlib
import tarfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_sdist", ROOT / "tools" / "check_sdist.py")
check_sdist = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_sdist)

PKG_INFO = "Metadata-Version: 2.4\nName: demplan\nVersion: 0.1.0\nLicense-File: LICENSE\n"


def _sdist(tmp_path, files):
    path = tmp_path / "demplan-0.1.0.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(f"demplan-0.1.0/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return str(path)


def test_missing_license_file_is_reported(tmp_path, capsys):
    path = _sdist(tmp_path, {"PKG-INFO": PKG_INFO})
    assert check_sdist.missing_license_files(path) == ["LICENSE"]
    assert check_sdist.main([path]) == 1
    assert "License-File LICENSE is declared but not in the archive" in capsys.readouterr().out


def test_present_license_file_passes(tmp_path):
    path = _sdist(tmp_path, {"PKG-INFO": PKG_INFO, "LICENSE": "MIT"})
    assert check_sdist.missing_license_files(path) == []
    assert check_sdist.main([path]) == 0


def test_license_file_in_a_subfolder_must_match_its_path(tmp_path):
    info = PKG_INFO.replace("License-File: LICENSE", "License-File: licenses/LICENSE")
    path = _sdist(tmp_path, {"PKG-INFO": info, "LICENSE": "MIT"})
    assert check_sdist.missing_license_files(path) == ["licenses/LICENSE"]
