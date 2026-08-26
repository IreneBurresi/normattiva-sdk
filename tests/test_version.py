import normattiva


def test_version_is_pep440() -> None:
    parts = normattiva.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
