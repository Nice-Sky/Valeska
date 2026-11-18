from arise import updater


def test_version_compare():
    assert updater.is_newer("v1.1.10", "1.1.9")
    assert not updater.is_newer("1.1.6", "1.1.6")
    assert not updater.is_newer("1.1.5", "1.1.6")
    assert updater.is_newer("1.2.0", "dev")      # versión de desarrollo: siempre hay más nueva
    assert not updater.is_newer("raro", "1.0.0")
