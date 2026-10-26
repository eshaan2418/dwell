from bench.privacy_scan import scan_blob

# fixtures are assembled at runtime so that the repo itself never contains address-like strings
ST, AVE = "Str" + "eet", "St" + "."
FAKE_ADDR = ("1" + "23 Queen " + ST + " West Apt 4").encode()
FAKE_ADDR2 = ("4" + "5 Bloor " + AVE + " Unit 1203").encode()
FAKE_KEY = ("-----BEGIN RSA " + "PRIVATE KEY-----").encode()


def test_detects_address_media_private_and_secrets():
    assert scan_blob("notes.md", b"we visited " + FAKE_ADDR, [])
    assert scan_blob("notes.md", b"lives at " + FAKE_ADDR2, [])
    assert scan_blob("data/private/units.csv", b"x", [])
    assert scan_blob("clip.mp4", b"x", [])
    assert scan_blob("a.wav", b"RIFF", [])
    assert scan_blob("k.txt", FAKE_KEY, [])
    assert scan_blob("firmware/include/config.h", b"", [])


def test_clean_text_passes():
    assert scan_blob("README.md", b"Direct-sun hours at 3 sites; Toronto grid rotated 16.7 deg.", []) == []
    fake = "1" + "2 Example " + ST
    assert scan_blob("x.md", fake.encode(), [fake]) == []
