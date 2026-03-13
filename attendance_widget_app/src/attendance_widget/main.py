from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from attendance_widget.ui import AttendanceWidget


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    widget = AttendanceWidget()
    widget.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
