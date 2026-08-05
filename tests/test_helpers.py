from steam_library_downloader.app import OwnedApp, _extract_percent, _safe_name


def test_percent():
    assert _extract_percent(" 42.50% file.bin") == 42.5
    assert _extract_percent("done") is None


def test_owned_app_json():
    app = OwnedApp.from_json({"AppId": 291550, "Name": "Brawlhalla", "Type": "game"})
    assert app.app_id == 291550
    assert app.name == "Brawlhalla"


def test_safe_name():
    assert _safe_name('A/B:C*D?') == "A-B-C-D-"
