import pytest

from kemocore.demo import make_image
from kemocore.timelapse.create import create_template
from kemocore.timelapse.project import TimelapseProject
from kemoserver.cli import main


def test_new_uses_template_name_and_refuses_overwrite(tmp_path, capsys):
    template = tmp_path / "調査 2026.11.tdb"
    create_template(template)
    root = tmp_path / "images"
    root.mkdir()
    make_image(root / "sample.JPG", None, "sample")

    main(["new", str(root), "--template", str(template)])

    assert capsys.readouterr().out == "1 files\n"
    ddb = root / "調査 2026.11.ddb"
    project = TimelapseProject(ddb)
    try:
        assert project.count({}) == 1
        assert project.file(1)["values"]["File"] == "sample.JPG"
    finally:
        project.close()

    before = ddb.read_bytes()
    with pytest.raises(FileExistsError):
        main(["new", str(root), "--template", str(template)])
    assert ddb.read_bytes() == before
