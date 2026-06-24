"""PySide6 desktop application host."""

from __future__ import annotations

import os
import sys
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMainWindow

from .bridge import DesktopBridge


def desktop_web_root() -> str:
    return os.path.join(os.path.dirname(__file__), "web")


def desktop_index_path() -> str:
    return os.path.join(desktop_web_root(), "index.html")


class DesktopMainWindow(QMainWindow):
    """Main OPC Desktop window with an embedded WebView dashboard."""

    def __init__(self, run_args: Any, bridge: DesktopBridge | None = None) -> None:
        super().__init__()
        self.setWindowTitle("OPC Desktop")
        self.resize(1440, 900)

        self.web_view = QWebEngineView(self)
        self.channel = QWebChannel(self.web_view.page())
        self.bridge = bridge or DesktopBridge(run_args, parent=self)
        self.channel.registerObject("desktopBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        self.web_view.setUrl(QUrl.fromLocalFile(desktop_index_path()))
        self.setCentralWidget(self.web_view)

        self.devtools_view: QWebEngineView | None = None
        if getattr(run_args, "desktop_devtools", False):
            self.devtools_view = QWebEngineView()
            self.devtools_view.setWindowTitle("OPC Desktop DevTools")
            self.devtools_view.resize(1100, 760)
            self.web_view.page().setDevToolsPage(self.devtools_view.page())
            self.devtools_view.show()


def run_desktop_app(run_args: Any) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = DesktopMainWindow(run_args)
    window.show()
    return int(app.exec())
