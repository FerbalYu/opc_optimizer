"""Static regression checks for the Web UI runtime overview."""

from pathlib import Path


INDEX_HTML = Path(__file__).resolve().parents[1] / "ui" / "web" / "index.html"


def _index_html() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


def test_runtime_overview_markup_exists():
    html = _index_html()

    assert 'id="workflow-overview"' in html
    assert 'id="node-state-grid"' in html
    assert 'id="overview-risk"' in html
    assert 'id="overview-files"' in html
    assert 'id="overview-errors"' in html
    assert 'id="overview-recent"' in html


def test_runtime_overview_styles_exist():
    html = _index_html()

    assert "#workflow-overview" in html
    assert ".node-state-cell.running" in html
    assert ".node-state-cell.done" in html
    assert ".node-state-cell.error" in html
    assert ".overview-risk.error" in html


def test_runtime_overview_event_hooks_exist():
    html = _index_html()

    assert "function initWorkflowOverview()" in html
    assert "function setNodeVisualState(nodeName, status)" in html
    assert "function resetNodeVisualState()" in html
    assert "function addOverviewEvent(label, detail = '')" in html
    assert "setNodeVisualState(data.node, 'running')" in html
    assert "setNodeVisualState(data.node, 'done')" in html
    assert "setNodeVisualState(data.node, 'error')" in html
    assert "visualState.changedFiles += data.files.length" in html
