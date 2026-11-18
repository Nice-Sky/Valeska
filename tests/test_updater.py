from arise import updater


def test_version_compare():
    assert updater.is_newer("v1.1.10", "1.1.9")
    assert not updater.is_newer("1.1.6", "1.1.6")
    assert not updater.is_newer("1.1.5", "1.1.6")
    assert updater.is_newer("1.2.0", "dev")      # versión de desarrollo: siempre hay más nueva
    assert not updater.is_newer("raro", "1.0.0")


def test_download_verifies_sha256(tmp_path):
    import hashlib
    import threading
    src = tmp_path / "instalador.exe"
    src.write_bytes(b"contenido de prueba" * 1000)
    good = hashlib.sha256(src.read_bytes()).hexdigest()
    results = {}
    for name, digest in (("ok", good), ("mal", "0" * 64)):
        ev = threading.Event()

        def done(path, err, name=name, ev=ev):
            results[name] = (path, err)
            ev.set()
        updater.download_async(src.as_uri(), lambda k: None, done, digest)
        assert ev.wait(10)
    assert results["ok"][0] and results["ok"][1] is None
    assert results["mal"][0] is None and "huella" in results["mal"][1]
