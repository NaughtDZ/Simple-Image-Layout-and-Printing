"""程序入口。

运行方式：
    python main.py
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from mainwindow import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("图片排版打印工具")
    app.setOrganizationName("imagererange")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
