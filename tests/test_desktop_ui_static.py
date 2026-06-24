"""Static checks for the desktop WebView UI."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP_WEB = ROOT / "ui" / "desktop" / "web"


def test_desktop_html_uses_qwebchannel_and_three_without_websocket():
    html = (DESKTOP_WEB / "index.html").read_text(encoding="utf-8")
    js = (DESKTOP_WEB / "app.js").read_text(encoding="utf-8")

    assert "qrc:///qtwebchannel/qwebchannel.js" in js
    assert '"three": "./vendor/three.module.js"' in html
    assert "new QWebChannel" in js
    assert "WebSocket" not in html
    assert "WebSocket" not in js


def test_desktop_ui_contains_required_dashboard_regions():
    html = (DESKTOP_WEB / "index.html").read_text(encoding="utf-8")

    for marker in [
        "sceneCanvas",
        "projectPath",
        "startBtn",
        "agentLoop",
        "toolCalls",
        "roundHistory",
        "insights",
        "logList",
    ]:
        assert marker in html


def test_desktop_three_asset_is_packaged_locally():
    asset = DESKTOP_WEB / "vendor" / "three.module.js"

    assert asset.is_file()
    assert "class WebGLRenderer" in asset.read_text(encoding="utf-8", errors="ignore")


def test_desktop_scene_preserves_office_worker_concept():
    js = (DESKTOP_WEB / "app.js").read_text(encoding="utf-8")

    for marker in [
        "function buildRoom",
        "function buildStation",
        "const steve = new THREE.Group",
        "buildDesk",
        "buildChair",
        "window.__opcDesktopHandleEvent",
    ]:
        assert marker in js

    for station in ["plan", "execute", "test", "archive", "report", "interact"]:
        assert station in js

    for office_prop in ["monitor", "sofa", "file", "insightBar"]:
        assert office_prop.lower() in js.lower()
