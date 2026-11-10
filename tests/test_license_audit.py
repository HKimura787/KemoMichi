from pathlib import Path

import pytest

from tools.license_audit import audit


def test_named_libraries_are_absent_from_current_dependencies():
    result = audit(Path(__file__).resolve().parents[1])
    assert result["matches"] == []
    assert result["checkedLibraries"] == {"NReco.VideoConverter": "not found", "SixLabors.ImageSharp": "not found"}


@pytest.mark.parametrize("filename", ["NReco.VideoConverter.dll", "SixLabors.ImageSharp.dll"])
def test_audit_rejects_restricted_libraries_in_a_bundle(tmp_path, filename):
    (tmp_path / filename).write_bytes(b"test fixture")
    with pytest.raises(RuntimeError, match="Restricted dependency"):
        audit(Path(__file__).resolve().parents[1], tmp_path)
