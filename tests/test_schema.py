from pathlib import Path

from publisher import schema


def test_release_file():
    assert schema.ReleaseFile(name=Path("a/b/c")).name == "a/b/c"
    assert schema.ReleaseFile(name=Path(r"a\b\c")).name == "a/b/c"
