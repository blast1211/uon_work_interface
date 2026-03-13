import sys
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QLabel
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QPixmap, QFontDatabase
from PyQt5.QtCore import Qt, QRectF, QPointF, QPoint

class OverwatchScoreWidget(QWidget):
    def __init__(self, teamA=40, teamB=15, roundsA=1, roundsB=2, scale=0.8):
        super().__init__()
        self.scale = scale
        self.resizing = False

        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        font_id = QFontDatabase.addApplicationFont("koverwatch.ttf")
        font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
        self.font_family = font_family

        self.blue_bg = QPixmap("blue.png")
        self.red_bg = QPixmap("red.png")

        self.bg_label = QLabel(self)
        self.bg_label.lower()

        self.score_label_A = QLabel(self)
        self.score_label_B = QLabel(self)
        for label in (self.score_label_A, self.score_label_B):
            label.setStyleSheet("color: white;")
            label.setAttribute(Qt.WA_TranslucentBackground)

        self.close_btn = QPushButton("\u2715", self)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: white;
                font-size: 12px;
                border: none;
            }
            QPushButton:hover {
                color: red;
            }
        """)
        self.close_btn.clicked.connect(self.close_and_exit)


        self.handle = QLabel(self)
        self.handle.setAttribute(Qt.WA_TranslucentBackground)

        self.old_pos = None
        self.old_geometry = self.geometry()
        self.updateScores(teamA, teamB, roundsA, roundsB)

    def close_and_exit(self):
        self.close()
        QApplication.quit()

    def updateScores(self, teamA, teamB, roundsA, roundsB):
        self.teamA = teamA
        self.teamB = teamB
        self.roundsA = roundsA
        self.roundsB = roundsB

        self.bg_pixmap = self.blue_bg if teamA > teamB else self.red_bg

        if teamA>teamB:
            self.score_label_A.setStyleSheet("color: white;")
            self.score_label_B.setStyleSheet("color: rgb(220,2,5);")
        else:
            self.score_label_B.setStyleSheet("color: white;")
            self.score_label_A.setStyleSheet("color: rgb(0,200,220);")

        scaled_width = int(self.bg_pixmap.width() * 0.3 * self.scale)
        scaled_height = int(self.bg_pixmap.height() * 0.3 * self.scale)

        # 기존 위치 유지하고 크기만 변경
        current_pos = self.pos()
        self.setGeometry(current_pos.x(), current_pos.y(), scaled_width, scaled_height)

        self.bg_label.setPixmap(self.bg_pixmap.scaled(scaled_width, scaled_height, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.bg_label.setGeometry(0, 0, scaled_width, scaled_height)

        self.close_btn.setGeometry(scaled_width - 10, 4, 15, 15)

        font_size = int(32 * self.scale)
        custom_font = QFont(self.font_family, font_size)
        custom_font.setItalic(True)

        self.score_label_A.setText(f"{self.teamA}%")
        self.score_label_B.setText(f"{self.teamB}%")
        self.score_label_A.setFont(custom_font)
        self.score_label_B.setFont(custom_font)

        self.score_label_A.setGeometry(int(15 * self.scale), int(9 * self.scale), int(100 * self.scale), int(80 * self.scale))
        self.score_label_B.setGeometry(scaled_width - int(85 * self.scale), int(9 * self.scale), int(100 * self.scale), int(80 * self.scale))

        self.handle.setGeometry(self.width() - 20, self.height() - 20, 20, 20)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # 우측 하단 ㄴ자 핸들 항상 일정 크기로 그리기
        painter.setPen(QPen(QColor(0, 0, 0, 100), 3))
        painter.drawLine(self.width() - 10, self.height() - 1, self.width() - 1, self.height() - 1)
        painter.drawLine(self.width() - 1, self.height() - 10, self.width() - 1, self.height() - 1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._is_on_handle(event.pos()):
                self.resizing = True
                self.start_pos = event.globalPos()
                self.start_scale = self.scale
            else:
                self.old_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if self.resizing:
            delta = event.globalPos() - self.start_pos
            new_scale = max(0.2, min(1.5, self.start_scale + delta.x() * 0.002))
            self.scale = new_scale
            self.updateScores(self.teamA, self.teamB, self.roundsA, self.roundsB)
        elif event.buttons() == Qt.LeftButton and self.old_pos:
            delta = event.globalPos() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        self.old_pos = None
        self.resizing = False

    def _is_on_handle(self, pos):
        return pos.x() >= self.width() - 10 and pos.y() >= self.height() - 10

if __name__ == '__main__':
    app = QApplication(sys.argv)
    widget = OverwatchScoreWidget()
    widget.show()
    sys.exit(app.exec_())
