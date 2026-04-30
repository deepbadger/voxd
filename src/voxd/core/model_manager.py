"""voxd.core.model_manager - Qt dialog for managing Whisper models.

Usage:
    from voxd.core.model_manager import show_model_manager
    show_model_manager(parent)
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QPushButton,
    QWidget, QHBoxLayout, QProgressBar, QMessageBox
)

from voxd.core.config import get_config
from voxd import models as mdl

_CFG = get_config()


# ---------------------------------------------------------------------------
#   Background downloader thread
# ---------------------------------------------------------------------------
class _DownloadThread(QThread):
    progress = pyqtSignal(int, int)  # downloaded, total
    finished_ok = pyqtSignal(Path)
    failed = pyqtSignal(str)

    def __init__(self, key: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._key = key

    def run(self):
        try:
            def _cb(done: int, total: int):
                self.progress.emit(done, total)

            path = mdl.ensure(self._key, quiet=True, progress_cb=_cb)
            self.finished_ok.emit(path)
        except Exception as e:
            self.failed.emit(str(e))


# ---------------------------------------------------------------------------
#   Dialog implementation
# ---------------------------------------------------------------------------
class ModelManager(QDialog):
    """Qt dialog that lists all models and allows install / remove / activate."""

    COL_NAME = 0
    COL_SIZE = 1
    COL_STATUS = 2
    COL_ACTION = 3

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Manage Whisper Models")
        self.setMinimumWidth(600)
        from voxd.core.voxd_core import DARK_DIALOG_QSS
        self.setStyleSheet(DARK_DIALOG_QSS + """
            QTableWidget { background-color: #1e1e1e; color: white; gridline-color: #444; }
            QHeaderView::section { background-color: #3a3a3a; color: white; border: 1px solid #555; padding: 4px; }
            QTableWidget::item:selected { background-color: #FF4500; color: white; }
        """)

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Size", "Status", "Action"])
        header = self.table.horizontalHeader()
        if header is not None:  # appease static checkers
            header.setStretchLastSection(True)
        layout.addWidget(self.table)

        self._populate()

    # ------------------------------------------------------------------
    def _populate(self):
        self.table.setRowCount(0)
        active_path = Path(_CFG.data.get("whisper_model_path", "")).name
        local_set = set(mdl.list_local())
        catalogue_fnames = {f"ggml-{k}.bin" for k in mdl.CATALOGUE.keys()}

        for key, (size_mb, *_rest) in mdl.CATALOGUE.items():
            row = self.table.rowCount()
            self.table.insertRow(row)

            fname = f"ggml-{key}.bin"
            # Name ----------------------------------------------------
            self.table.setItem(row, self.COL_NAME, QTableWidgetItem(fname))
            # Size ----------------------------------------------------
            self.table.setItem(row, self.COL_SIZE, QTableWidgetItem(f"{size_mb} MB"))

            # Status --------------------------------------------------
            if fname == active_path:
                status = "Active"
            elif fname in local_set:
                status = "Installed"
            else:
                status = "Remote"
            self.table.setItem(row, self.COL_STATUS, QTableWidgetItem(status))

            # Action widget -------------------------------------------
            cell_widget: QWidget
            if status == "Active":
                cell_widget = QWidget()  # empty (could add label)
            elif status == "Installed":
                cell_widget = self._make_installed_actions(key)
            else:  # Remote
                cell_widget = self._make_download_action(key)

            self.table.setCellWidget(row, self.COL_ACTION, cell_widget)
            if status == "Active":
                self._mark_active_row(row)

        # Custom local models (dropped into the models dir, not in CATALOGUE) ──
        for fname in sorted(local_set - catalogue_fnames):
            path = mdl.CACHE_DIR / fname
            try:
                size_mb = max(1, path.stat().st_size // (1024 * 1024))
            except OSError:
                size_mb = 0

            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, self.COL_NAME, QTableWidgetItem(fname))
            self.table.setItem(row, self.COL_SIZE, QTableWidgetItem(f"{size_mb} MB"))

            is_active = (fname == active_path)
            self.table.setItem(
                row, self.COL_STATUS,
                QTableWidgetItem("Active (custom)" if is_active else "Custom"),
            )
            cell_widget = QWidget() if is_active else self._make_custom_actions(fname)
            self.table.setCellWidget(row, self.COL_ACTION, cell_widget)
            if is_active:
                self._mark_active_row(row)

        self.table.resizeColumnsToContents()

    def _mark_active_row(self, row: int):
        for col in range(0, 4):
            item = self.table.item(row, col)
            if item:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                item.setForeground(Qt.GlobalColor.darkGreen)
                font = item.font()
                font.setBold(True)
                item.setFont(font)

    # ------------------------------------------------------------------
    def _make_installed_actions(self, key: str) -> QWidget:
        w = QWidget()
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)

        btn_activate = QPushButton("Activate")
        btn_remove = QPushButton("Remove")
        hl.addWidget(btn_activate)
        hl.addWidget(btn_remove)

        btn_activate.clicked.connect(lambda _=False, k=key: self._on_activate(k))
        btn_remove.clicked.connect(lambda _=False, k=key: self._on_remove(k))
        return w

    def _make_download_action(self, key: str) -> QWidget:
        w = QWidget()
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)

        btn_dl = QPushButton("Download")
        hl.addWidget(btn_dl)

        btn_dl.clicked.connect(lambda _=False, k=key: self._start_download(k, w))
        return w

    def _make_custom_actions(self, fname: str) -> QWidget:
        w = QWidget()
        hl = QHBoxLayout(w)
        hl.setContentsMargins(0, 0, 0, 0)

        btn_activate = QPushButton("Activate")
        btn_remove = QPushButton("Remove")
        hl.addWidget(btn_activate)
        hl.addWidget(btn_remove)

        btn_activate.clicked.connect(lambda _=False, f=fname: self._on_activate_custom(f))
        btn_remove.clicked.connect(lambda _=False, f=fname: self._on_remove_custom(f))
        return w

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------
    def _on_activate(self, key: str):
        mdl.set_active(key)
        _CFG.load()  # refresh singleton
        self._populate()

    def _on_remove(self, key: str):
        mdl.remove(key)
        if Path(_CFG.data.get("whisper_model_path", "")).name == f"ggml-{key}.bin":
            _CFG.set("whisper_model_path", "")
            _CFG.save()
        self._populate()

    def _on_activate_custom(self, fname: str):
        path = mdl.CACHE_DIR / fname
        if not path.exists():
            QMessageBox.warning(self, "Activate failed", f"File not found:\n{path}")
            self._populate()
            return
        _CFG.set("whisper_model_path", str(path.resolve()))
        _CFG.save()
        _CFG.load()  # re-resolve paths and broadcast to running components
        self._populate()

    def _on_remove_custom(self, fname: str):
        path = mdl.CACHE_DIR / fname
        if path.exists():
            try:
                path.unlink()
            except OSError as e:
                QMessageBox.warning(self, "Remove failed", str(e))
                return
        if Path(_CFG.data.get("whisper_model_path", "")).name == fname:
            _CFG.set("whisper_model_path", "")
            _CFG.save()
        self._populate()

    def _start_download(self, key: str, cell_widget: QWidget):
        # replace button with progress bar
        pb = QProgressBar()
        pb.setRange(0, 100)
        layout = cell_widget.layout()
        if layout is not None:
            for i in reversed(range(layout.count())):
                item = layout.itemAt(i)
                if item is not None:
                    w = item.widget()
                    if w is not None:
                        w.deleteLater()
            layout.addWidget(pb)

        thread = _DownloadThread(key)
        thread.progress.connect(lambda done, total: pb.setValue(int(done / total * 100)))

        def _done(path: Path):
            thread.deleteLater()
            self._populate()
            QMessageBox.information(self, "Download complete", f"Installed {path.name}")

        def _fail(msg: str):
            thread.deleteLater()
            QMessageBox.warning(self, "Download failed", msg)
            self._populate()

        thread.finished_ok.connect(_done)
        thread.failed.connect(_fail)
        thread.start()


# ---------------------------------------------------------------------------
#   Convenience wrapper
# ---------------------------------------------------------------------------

def show_model_manager(parent: QWidget | None = None):
    dlg = ModelManager(parent)
    dlg.exec()
    return dlg 