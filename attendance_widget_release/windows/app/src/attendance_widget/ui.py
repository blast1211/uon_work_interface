from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QSettings, QThread, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from attendance_widget.automation import AttendanceAutomation, AttendanceError, AttendanceSnapshot
from attendance_widget.calculations import normalize_times, target_minutes_for_label, week_date_strings, worked_minutes
from attendance_widget.config import load_settings


ASSET_ROOT = Path(__file__).resolve().parents[3]
FONT_PATH = ASSET_ROOT / "koverwatch.ttf"
BLUE_PATH = ASSET_ROOT / "overwatch_blue_new.png"
RED_PATH  = ASSET_ROOT / "overwatch_red_new.png"
DAY_NAMES = ["월", "화", "수", "목", "금"]
REFRESH_INTERVAL_MS = 10_000
SETTINGS_ORG = "Chansol"
SETTINGS_APP = "AttendanceWidget"


class SessionWorker(QObject):
    login_succeeded = Signal(object)
    action_succeeded = Signal(object, str)
    failed = Signal(str)
    shutdown_complete = Signal()

    def __init__(self, settings) -> None:
        super().__init__()
        self.settings = settings
        self.automation: AttendanceAutomation | None = None

    @Slot(str, str)
    def login(self, username: str, password: str) -> None:
        try:
            if self.automation is not None:
                self.automation.close()
            self.automation = AttendanceAutomation(self.settings)
            self.automation.login(username=username, password=password)
            self.automation.open_weekly_page()
            snapshot = self.automation.fetch_snapshot()
            self.login_succeeded.emit(snapshot)
        except Exception as exc:
            self.failed.emit(str(exc))

    @Slot()
    def refresh_snapshot(self) -> None:
        try:
            automation = self._require_automation()
            automation.open_weekly_page()
            snapshot = automation.fetch_snapshot()
            self.action_succeeded.emit(snapshot, "refresh")
        except Exception as exc:
            self.failed.emit(str(exc))

    @Slot()
    def work_in(self) -> None:
        try:
            automation = self._require_automation()
            automation.click_work_in()
            automation.open_weekly_page()
            snapshot = automation.fetch_snapshot()
            self.action_succeeded.emit(snapshot, "work_in")
        except Exception as exc:
            self.failed.emit(str(exc))

    @Slot()
    def work_out(self) -> None:
        try:
            automation = self._require_automation()
            automation.click_work_out()
            automation.open_weekly_page()
            snapshot = automation.fetch_snapshot()
            self.action_succeeded.emit(snapshot, "work_out")
        except Exception as exc:
            self.failed.emit(str(exc))

    @Slot()
    def shutdown(self) -> None:
        if self.automation is not None:
            try:
                self.automation.close()
            except Exception:
                pass
            self.automation = None
        self.shutdown_complete.emit()

    def _require_automation(self) -> AttendanceAutomation:
        if self.automation is None:
            raise AttendanceError("먼저 접속을 해주세요.")
        return self.automation


class DayRowWidget(QFrame):
    def __init__(self, day_name: str, font_family: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.day_name = day_name
        self.balance_minutes = 0
        self.come_time = "--:--"
        self.leave_time = "--:--"
        self.expanded = False
        self.max_minutes = 1
        self.font_family = font_family
        self.row_font = QFont(font_family, 13)
        self.row_font.setItalic(False)
        self.row_font.setBold(False)
        self.row_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        self.detail_font = QFont(font_family, 12)
        self.detail_font.setItalic(False)
        self.detail_font.setBold(False)
        self.detail_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)

        self.setStyleSheet(
            f"QFrame {{ background: transparent; border: none; font-family: '{font_family}'; }}"
            f"QLabel {{ color: white; font-family: '{font_family}'; font-weight: 400; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self.header = QFrame(self)
        self.header.setCursor(Qt.PointingHandCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(4, 6, 4, 6)
        header_layout.setSpacing(8)

        self.arrow_label = QLabel(">", self.header)
        self.arrow_label.setFixedWidth(12)
        self.arrow_label.setFont(self.row_font)
        header_layout.addWidget(self.arrow_label)

        self.day_label = QLabel(day_name, self.header)
        self.day_label.setFixedWidth(30)
        self.day_label.setFont(self.row_font)
        header_layout.addWidget(self.day_label)

        self.bar_track = QFrame(self.header)
        self.bar_track.setMinimumHeight(12)
        self.bar_track.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.bar_track.setStyleSheet("QFrame { background: rgba(255,255,255,0.08); border-radius: 6px; }")
        self.bar_fill = QFrame(self.bar_track)
        self.bar_fill.setGeometry(0, 0, 0, 12)
        self.bar_fill.setStyleSheet("QFrame { background: #ff5a5a; border-radius: 6px; }")
        header_layout.addWidget(self.bar_track, 1)

        self.balance_label = QLabel("0:00", self.header)
        self.balance_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.balance_label.setFixedWidth(64)
        self.balance_label.setFont(self.row_font)
        header_layout.addWidget(self.balance_label)

        outer.addWidget(self.header)

        self.detail_label = QLabel(self)
        self.detail_label.setVisible(False)
        self.detail_label.setTextFormat(Qt.RichText)
        self.detail_label.setFont(self.detail_font)
        self.detail_label.setStyleSheet(f"color: rgba(255,255,255,0.76); font-family: '{font_family}';")
        outer.addWidget(self.detail_label)

        self.set_row_data(0, "--:--", "--:--", 1)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.toggle()
        super().mousePressEvent(event)

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self.detail_label.setVisible(self.expanded)
        self.arrow_label.setText("v" if self.expanded else ">")
        self.adjustSize()

    def set_row_data(self, balance_minutes: int, come_time: str, leave_time: str, max_minutes: int) -> None:
        self.balance_minutes = balance_minutes
        self.come_time = come_time
        self.leave_time = leave_time
        self.max_minutes = max(max_minutes, 1)
        self.balance_label.setText(self._format_balance(balance_minutes))
        self.detail_label.setText(
            "&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:#57c7ff;'>출근</span> "
            f"{come_time}<br>&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:#ff8c5a;'>퇴근</span> {leave_time}"
        )

        color = "#ff5a5a" if balance_minutes >= 0 else "#3aa7ff"
        self.balance_label.setStyleSheet(f"color: {color};")
        self.bar_fill.setStyleSheet(f"QFrame {{ background: {color}; border-radius: 6px; }}")
        self._update_bar()

    def resizeEvent(self, event) -> None:
        self._update_bar()
        super().resizeEvent(event)

    def _update_bar(self) -> None:
        track_width = max(self.bar_track.width(), 1)
        ratio = abs(self.balance_minutes) / self.max_minutes
        fill_width = max(8 if abs(self.balance_minutes) > 0 else 0, int(track_width * ratio))
        self.bar_fill.setGeometry(0, 0, fill_width, self.bar_track.height())

    def _format_balance(self, minutes: int) -> str:
        sign = "+" if minutes >= 0 else "-"
        hours, remain = divmod(abs(minutes), 60)
        return f"{sign}{hours}:{remain:02d}"


class AttendanceWidget(QWidget):
    login_requested = Signal(str, str)
    refresh_requested = Signal()
    work_in_requested = Signal()
    work_out_requested = Signal()
    shutdown_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.scale = 0.8
        self.resizing = False
        self.old_pos: QPoint | None = None
        self.snapshot: AttendanceSnapshot | None = None
        self.is_logged_in = False
        self.is_busy = False
        self.current_balance_minutes = 0
        self.score_text_left = "0:00%"
        self.score_text_right = "0:00%"
        self.card_pixmap = QPixmap()
        self.card_loading = False
        self.qt_settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._load_assets()
        self._build_worker()
        self._build_ui()
        self._build_timer()
        self._load_saved_preferences()
        self._update_score_card(0)
        self._set_logged_in_ui(False)

    def _display_font(self, size: int, italic: bool = False) -> QFont:
        font = QFont(self.font_family, size)
        font.setItalic(italic)
        font.setBold(False)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        return font

    def _build_worker(self) -> None:
        self.session_thread = QThread(self)
        self.worker = SessionWorker(self.settings)
        self.worker.moveToThread(self.session_thread)
        self.login_requested.connect(self.worker.login)
        self.refresh_requested.connect(self.worker.refresh_snapshot)
        self.work_in_requested.connect(self.worker.work_in)
        self.work_out_requested.connect(self.worker.work_out)
        self.shutdown_requested.connect(self.worker.shutdown)
        self.worker.login_succeeded.connect(self._handle_login_success)
        self.worker.action_succeeded.connect(self._handle_action_success)
        self.worker.failed.connect(self._handle_worker_failure)
        self.worker.shutdown_complete.connect(self.session_thread.quit)
        self.session_thread.start()

    def _load_assets(self) -> None:
        font_id = QFontDatabase.addApplicationFont(str(FONT_PATH))
        font_families = QFontDatabase.applicationFontFamilies(font_id)
        self.font_family = font_families[0] if font_families else "Arial"
        self.blue_bg = QPixmap(str(BLUE_PATH))
        self.red_bg = QPixmap(str(RED_PATH))
        self.card_pixmap = self.blue_bg if not self.blue_bg.isNull() else QPixmap()
        self.blue_bg_dim = self._make_dimmed_pixmap(self.blue_bg)
        self.red_bg_dim = self._make_dimmed_pixmap(self.red_bg)

    def _make_dimmed_pixmap(self, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return QPixmap()
        image = pixmap.toImage().convertToFormat(pixmap.toImage().format())
        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                gray = int(color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114)
                color.setRed(gray)
                color.setGreen(gray)
                color.setBlue(gray)
                image.setPixelColor(x, y, color)
        return QPixmap.fromImage(image)

    def _build_timer(self) -> None:
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        self.refresh_timer.timeout.connect(self.refresh_snapshot)

    def _build_ui(self) -> None:
        self.setWindowTitle("근태 위젯")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)
        root.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.card = QWidget(self)
        self.card.setAttribute(Qt.WA_TranslucentBackground)
        self.bg_label = QLabel(self.card)
        self.bg_label.lower()

        self.score_label_left = QLabel(self.card)
        self.score_label_right = QLabel(self.card)
        score_font = self._display_font(25, italic=True)
        for label in (self.score_label_left, self.score_label_right):
            label.setAlignment(Qt.AlignCenter)
            label.setFont(score_font)
            label.setStyleSheet("color: white; background: transparent;")

        root.addWidget(self.card, alignment=Qt.AlignLeft)

        self.details_panel = QFrame(self)
        self.details_panel.setVisible(False)
        self.details_panel.setStyleSheet(
            "QFrame { background: rgba(0,0,0,26); border: none; border-radius: 14px; }"
            f"QLabel {{ color: white; font-family: '{self.font_family}'; font-weight: 400; }}"
            f"QPushButton {{ background: rgba(255,255,255,0.12); color: white; border: none; border-radius: 8px; padding: 10px 12px; font-family: '{self.font_family}'; font-weight: 400; font-size: 15px; }}"
            "QPushButton:hover { background: rgba(255,255,255,0.2); }"
            "QPushButton:disabled { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.35); }"
            f"QCheckBox {{ color: white; font-family: '{self.font_family}'; font-weight: 400; font-size: 14px; }}"
        )
        details_layout = QVBoxLayout(self.details_panel)
        details_layout.setContentsMargins(16, 14, 16, 14)
        details_layout.setSpacing(12)
        details_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        credentials_col = QVBoxLayout()
        credentials_col.setSpacing(10)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("아이디")
        credentials_col.addWidget(self.username_input)
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("비밀번호")
        self.password_input.setEchoMode(QLineEdit.Password)
        credentials_col.addWidget(self.password_input)
        top_row.addLayout(credentials_col, 1)

        self.login_button = QPushButton("접속")
        self.login_button.setFixedWidth(92)
        self.login_button.setFont(self._display_font(15))
        self.login_button.clicked.connect(self.login_to_site)
        top_row.addWidget(self.login_button, alignment=Qt.AlignBottom)
        details_layout.addLayout(top_row)

        self.headless_checkbox = QCheckBox("크롬 헤드리스")
        self.headless_checkbox.setFont(self._display_font(14))
        self.headless_checkbox.toggled.connect(self._on_headless_toggled)
        details_layout.addWidget(self.headless_checkbox, alignment=Qt.AlignHCenter)

        self.always_on_top_checkbox = QCheckBox("항상 위에 표시")
        self.always_on_top_checkbox.setFont(self._display_font(14))
        self.always_on_top_checkbox.toggled.connect(self._on_always_on_top_toggled)
        details_layout.addWidget(self.always_on_top_checkbox, alignment=Qt.AlignHCenter)

        opacity_title = QLabel("전체 투명도")
        opacity_title.setFont(self._display_font(15))
        details_layout.addWidget(opacity_title, alignment=Qt.AlignLeft)

        opacity_row = QHBoxLayout()
        opacity_row.setSpacing(10)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(10, 90)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self.opacity_slider, 1)
        self.opacity_value_label = QLabel("50%")
        self.opacity_value_label.setFont(self._display_font(14))
        opacity_row.addWidget(self.opacity_value_label)
        details_layout.addLayout(opacity_row)

        refresh_title = QLabel("새로고침 주기")
        refresh_title.setFont(self._display_font(15))
        details_layout.addWidget(refresh_title, alignment=Qt.AlignLeft)

        refresh_row = QHBoxLayout()
        refresh_row.setSpacing(10)
        self.refresh_interval_slider = QSlider(Qt.Horizontal)
        self.refresh_interval_slider.setRange(10, 300)
        self.refresh_interval_slider.valueChanged.connect(self._on_refresh_interval_changed)
        refresh_row.addWidget(self.refresh_interval_slider, 1)
        self.refresh_interval_value_label = QLabel("10초")
        self.refresh_interval_value_label.setFont(self._display_font(14))
        refresh_row.addWidget(self.refresh_interval_value_label)
        details_layout.addLayout(refresh_row)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.refresh_button = QPushButton("새로고침")
        self.work_in_button = QPushButton("출근")
        self.work_out_button = QPushButton("퇴근")
        self.exit_button = QPushButton("종료")
        for button in (self.refresh_button, self.work_in_button, self.work_out_button, self.exit_button):
            button.setFont(self._display_font(15))
        self.refresh_button.clicked.connect(self.refresh_snapshot)
        self.work_in_button.clicked.connect(self.work_in)
        self.work_out_button.clicked.connect(self.work_out)
        self.exit_button.clicked.connect(self.close_and_exit)
        action_row.addWidget(self.refresh_button)
        action_row.addWidget(self.work_in_button)
        action_row.addWidget(self.work_out_button)
        action_row.addWidget(self.exit_button)
        details_layout.addLayout(action_row)

        self.login_spinner = QProgressBar(self)
        self.login_spinner.setRange(0, 0)
        self.login_spinner.setTextVisible(False)
        self.login_spinner.setFixedHeight(8)
        self.login_spinner.setVisible(False)
        self.login_spinner.setStyleSheet(
            "QProgressBar { background: rgba(255,255,255,0.07); border: none; border-radius: 4px; }"
            "QProgressBar::chunk { background: #4ec9f5; border-radius: 4px; }"
        )
        details_layout.addWidget(self.login_spinner)

        self.status_label = QLabel("접속하면 숨겨진 브라우저 세션이 시작됩니다.")
        self.status_label.setFont(self._display_font(14))
        self.status_label.setStyleSheet(f"color: rgba(255,255,255,0.78); font-family: '{self.font_family}';")
        details_layout.addWidget(self.status_label, alignment=Qt.AlignHCenter)

        self.day_rows: list[DayRowWidget] = []
        for day_name in DAY_NAMES:
            row = DayRowWidget(day_name, self.font_family, self.details_panel)
            self.day_rows.append(row)
            details_layout.addWidget(row)

        root.addWidget(self.details_panel, alignment=Qt.AlignHCenter)
        self._apply_card_geometry()
        self.adjustSize()


    def _apply_details_background(self, opacity_percent: int) -> None:
        opacity_percent = max(10, min(90, opacity_percent))
        background_percent = opacity_percent * (80 / 90)
        alpha = int(255 * (background_percent / 100))
        self.details_panel.setStyleSheet(
            f"QFrame {{ background: rgba(0,0,0,{alpha}); border: none; border-radius: 14px; }}"
            f"QLabel {{ color: white; font-family: '{self.font_family}'; font-weight: 400; }}"
            f"QPushButton {{ background: rgba(255,255,255,0.12); color: white; border: none; border-radius: 8px; padding: 10px 12px; font-family: '{self.font_family}'; font-weight: 400; font-size: 15px; }}"
            "QPushButton:hover { background: rgba(255,255,255,0.2); }"
            "QPushButton:disabled { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.35); }"
            f"QCheckBox {{ color: white; font-family: '{self.font_family}'; font-weight: 400; font-size: 14px; }}"
        )

    def _format_refresh_interval(self, seconds: int) -> str:
        if seconds >= 60:
            minutes, remain = divmod(seconds, 60)
            if remain == 0:
                return f"{minutes}분"
            return f"{minutes}분 {remain}초"
        return f"{seconds}초"
    def _load_saved_preferences(self) -> None:
        self.username_input.setText(self.qt_settings.value("username", self.settings.username, type=str) or "")
        self.password_input.setText(self.qt_settings.value("password", self.settings.password, type=str) or "")
        saved_headless = self.qt_settings.value("headless", self.settings.headless, type=bool)
        self.settings.headless = bool(saved_headless)
        self.headless_checkbox.setChecked(self.settings.headless)

        saved_always_on_top = self.qt_settings.value("always_on_top", True, type=bool)
        self.always_on_top_checkbox.setChecked(bool(saved_always_on_top))
        self._apply_window_flags(bool(saved_always_on_top))

        saved_opacity = self.qt_settings.value("window_opacity", 90, type=int)
        saved_opacity = max(10, min(90, int(saved_opacity)))
        self.opacity_slider.setValue(saved_opacity)
        self.setWindowOpacity(saved_opacity / 100)
        self._apply_details_background(saved_opacity)
        self.opacity_value_label.setText(f"{saved_opacity}%")

        saved_interval = self.qt_settings.value("refresh_interval_seconds", 10, type=int)
        saved_interval = max(10, min(300, int(saved_interval)))
        self.refresh_interval_slider.setValue(saved_interval)
        self.refresh_timer.setInterval(saved_interval * 1000)
        self.refresh_interval_value_label.setText(self._format_refresh_interval(saved_interval))

    def _save_preferences(self) -> None:
        self.qt_settings.setValue("username", self.username_input.text().strip())
        self.qt_settings.setValue("password", self.password_input.text())
        self.qt_settings.setValue("headless", self.headless_checkbox.isChecked())
        self.qt_settings.setValue("always_on_top", self.always_on_top_checkbox.isChecked())
        self.qt_settings.setValue("window_opacity", self.opacity_slider.value())
        self.qt_settings.setValue("refresh_interval_seconds", self.refresh_interval_slider.value())
        self.qt_settings.sync()

    def _on_headless_toggled(self, checked: bool) -> None:
        self.settings.headless = checked
        self.qt_settings.setValue("headless", checked)
        self.qt_settings.sync()

    def _on_always_on_top_toggled(self, checked: bool) -> None:
        self._apply_window_flags(checked)
        self.qt_settings.setValue("always_on_top", checked)
        self.qt_settings.sync()

    def _on_opacity_changed(self, value: int) -> None:
        value = max(10, min(90, value))
        self.setWindowOpacity(value / 100)
        self._apply_details_background(value)
        self.opacity_value_label.setText(f"{value}%")
        self.qt_settings.setValue("window_opacity", value)

    def _on_refresh_interval_changed(self, value: int) -> None:
        value = max(10, min(300, value))
        self.refresh_timer.setInterval(value * 1000)
        self.refresh_interval_value_label.setText(self._format_refresh_interval(value))
        self.qt_settings.setValue("refresh_interval_seconds", value)

    def close_and_exit(self) -> None:
        self.refresh_timer.stop()
        self.shutdown_requested.emit()
        self.session_thread.quit()
        self.session_thread.wait(2000)
        self.close()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        self.refresh_timer.stop()
        self.shutdown_requested.emit()
        self.session_thread.quit()
        self.session_thread.wait(2000)
        super().closeEvent(event)

    def login_to_site(self) -> None:
        if self.is_busy or self.is_logged_in:
            return
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            QMessageBox.warning(self, "근태 위젯", "아이디와 비밀번호를 입력해주세요.")
            return
        self._save_preferences()
        self._set_busy(True, "초과근무 페이지에 접속 중입니다...")
        self.login_requested.emit(username, password)

    def refresh_snapshot(self) -> None:
        if self.is_busy or not self.is_logged_in:
            return
        self._set_busy(True, "초과근무 데이터를 갱신하는 중입니다...")
        self.refresh_requested.emit()

    def work_in(self) -> None:
        if self.is_busy or not self.is_logged_in:
            QMessageBox.information(self, "근태 위젯", "먼저 접속해서 같은 세션을 사용해주세요.")
            return
        self._set_busy(True, "출근 처리를 전송하는 중입니다...")
        self.work_in_requested.emit()

    def work_out(self) -> None:
        if self.is_busy or not self.is_logged_in:
            QMessageBox.information(self, "근태 위젯", "먼저 접속해서 같은 세션을 사용해주세요.")
            return
        self._set_busy(True, "퇴근 처리를 전송하는 중입니다...")
        self.work_out_requested.emit()

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self.is_busy = busy
        self.login_spinner.setVisible(busy)
        if busy and not self.is_logged_in:
            self.card_loading = True
            self._update_score_card(self.current_balance_minutes)
        elif not busy:
            self.card_loading = False
            self._update_score_card(self.current_balance_minutes)
        self.refresh_button.setEnabled(self.is_logged_in and not busy)
        self.work_in_button.setEnabled(self.is_logged_in and not busy)
        self.work_out_button.setEnabled(self.is_logged_in and not busy)
        if not self.is_logged_in:
            self.login_button.setEnabled(not busy)
            self.headless_checkbox.setEnabled(not busy)
        if message:
            self.status_label.setText(message)

    def _set_logged_in_ui(self, logged_in: bool) -> None:
        self.is_logged_in = logged_in
        self.username_input.setEnabled(not logged_in)
        self.password_input.setEnabled(not logged_in)
        self.login_button.setEnabled(not logged_in and not self.is_busy)
        self.headless_checkbox.setEnabled(not logged_in and not self.is_busy)
        self.refresh_button.setEnabled(logged_in and not self.is_busy)
        self.work_in_button.setEnabled(logged_in and not self.is_busy)
        self.work_out_button.setEnabled(logged_in and not self.is_busy)

    def _handle_login_success(self, snapshot: AttendanceSnapshot) -> None:
        self._set_logged_in_ui(True)
        self.snapshot = snapshot
        self._update_summary_ui(snapshot)
        self.status_label.setText("접속 완료. 숨겨진 브라우저 세션이 초과근무 페이지에서 실행 중입니다.")
        self.refresh_timer.start()
        self._set_busy(False)

    def _handle_action_success(self, snapshot: AttendanceSnapshot, action: str) -> None:
        self.snapshot = snapshot
        self._update_summary_ui(snapshot)
        if action == "work_in":
            self.status_label.setText("출근 처리를 현재 세션으로 전송했습니다.")
        elif action == "work_out":
            self.status_label.setText("퇴근 처리를 현재 세션으로 전송했습니다.")
        else:
            self.status_label.setText("초과근무 데이터를 갱신했습니다.")
        self._set_busy(False)

    def _handle_worker_failure(self, message: str) -> None:
        self._set_busy(False)
        QMessageBox.critical(self, "근태 위젯", message)

    def _update_summary_ui(self, snapshot: AttendanceSnapshot) -> None:
        balance_minutes = snapshot.summary.balance_minutes
        self._update_score_card(balance_minutes)
        self.status_label.setText(
            f"누적 {snapshot.summary.week_minutes // 60}h {(snapshot.summary.week_minutes % 60):02d}m / "
            f"기준 {snapshot.summary.expected_minutes // 60}h {(snapshot.summary.expected_minutes % 60):02d}m"
        )
        self._update_day_rows(snapshot)

    def _update_score_card(self, balance_minutes: int) -> None:
        self.current_balance_minutes = balance_minutes
        self.score_text_left = f"{self._format_duration(abs(min(balance_minutes, 0)))}%"
        self.score_text_right = f"{self._format_duration(max(balance_minutes, 0))}%"
        base_pixmap = self.red_bg if balance_minutes >= 0 else self.blue_bg
        if self.card_loading:
            self.card_pixmap = self.red_bg_dim if balance_minutes >= 0 else self.blue_bg_dim
        else:
            self.card_pixmap = base_pixmap

        if balance_minutes >= 0:
            self.score_label_left.setStyleSheet("color: rgb(0,200,220); background: transparent;")
            self.score_label_right.setStyleSheet("color: black; background: transparent;")
        else:
            self.score_label_left.setStyleSheet("color: black; background: transparent;")
            self.score_label_right.setStyleSheet("color: rgb(220,2,5); background: transparent;")

        self.score_label_left.setText(self.score_text_left)
        self.score_label_right.setText(self.score_text_right)
        self._apply_card_geometry()

    def _update_day_rows(self, snapshot: AttendanceSnapshot) -> None:
        rows_by_date = {row.date: row for row in snapshot.weekly_rows}
        target_dates = week_date_strings(date.today())
        day_data: list[tuple[int, str, str]] = []
        for day_key in target_dates:
            row = rows_by_date.get(day_key)
            if row is None:
                day_data.append((0, "--:--", "--:--"))
                continue
            come_time, leave_time = normalize_times(row, self.settings.default_start, self.settings.default_end)
            worked = worked_minutes(come_time, leave_time)
            expected = target_minutes_for_label(row.label, self.settings.weekday_target_minutes, self.settings.halfday_target_minutes)
            balance_minutes = worked - expected
            day_data.append((balance_minutes, self._format_clock(come_time), self._format_clock(leave_time)))

        max_minutes = max((abs(balance) for balance, _, _ in day_data), default=1)
        max_minutes = max(max_minutes, 1)
        for row_widget, (balance_minutes, come_time, leave_time) in zip(self.day_rows, day_data):
            row_widget.set_row_data(balance_minutes, come_time, leave_time, max_minutes)

    def _toggle_details(self, checked: bool) -> None:
        self.details_panel.setVisible(checked)
        self.adjustSize()
        self.update()

    def _apply_window_flags(self, always_on_top: bool) -> None:
        geometry = self.geometry()
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, always_on_top)
        if was_visible:
            self.show()
            self.setGeometry(geometry)

    def _apply_card_geometry(self) -> None:
        active_pixmap = self.card_pixmap if not self.card_pixmap.isNull() else self.blue_bg
        scaled_width = int(active_pixmap.width() * 0.3 * self.scale) if not active_pixmap.isNull() else 260
        scaled_height = int(active_pixmap.height() * 0.3 * self.scale) if not active_pixmap.isNull() else 90
        self.card.setFixedSize(scaled_width, scaled_height)
        self.details_panel.setFixedWidth(scaled_width)

        if not active_pixmap.isNull():
            scaled = active_pixmap.scaled(scaled_width, scaled_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.bg_label.setPixmap(scaled)
            self.bg_label.setGeometry(0, 0, scaled_width, scaled_height)

        score_font = self._display_font(max(12, int(25 * self.scale)), italic=True)
        self.score_label_left.setFont(score_font)
        self.score_label_right.setFont(score_font)
        self.score_label_left.setGeometry(int(-24 * self.scale), int(13 * self.scale), int(150 * self.scale), int(72 * self.scale))
        self.score_label_right.setGeometry(scaled_width - int(114 * self.scale), int(13 * self.scale), int(126 * self.scale), int(72 * self.scale))
        self.update()

    def _format_duration(self, minutes: int) -> str:
        hours, remain = divmod(abs(minutes), 60)
        return f"{hours}:{remain:02d}"

    def _format_clock(self, value: str) -> str:
        if len(value) < 4:
            return "--:--"
        return f"{value[:2]}:{value[2:4]}"

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            if self._is_on_handle(event.position().toPoint()):
                self.resizing = True
                self.start_pos = event.globalPosition().toPoint()
                self.start_scale = self.scale
                return
            clicked = self.childAt(event.position().toPoint())
            if clicked is not None and clicked is not self and clicked is not self.card and clicked is not self.bg_label:
                self.old_pos = None
                self.resizing = False
                event.accept()
                return
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event) -> None:
        if self.resizing:
            delta = event.globalPosition().toPoint() - self.start_pos
            self.scale = max(0.55, min(1.4, self.start_scale + delta.x() * 0.002))
            self._apply_card_geometry()
            self.adjustSize()
        elif event.buttons() == Qt.LeftButton and self.old_pos is not None:
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event) -> None:
        self.old_pos = None
        self.resizing = False

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.card.geometry().contains(event.position().toPoint()):
            self._toggle_details(not self.details_panel.isVisible())
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, event) -> None:
        if not self.details_panel.isVisible():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(0, 0, 0, 100), 3))
        target = self.details_panel.geometry()
        painter.drawLine(target.x() + target.width() - 10, target.y() + target.height() - 1, target.x() + target.width() - 1, target.y() + target.height() - 1)
        painter.drawLine(target.x() + target.width() - 1, target.y() + target.height() - 10, target.x() + target.width() - 1, target.y() + target.height() - 1)

    def _is_on_handle(self, pos: QPoint) -> bool:
        if not self.details_panel.isVisible():
            return False
        target_rect = self.details_panel.geometry()
        return pos.x() >= target_rect.right() - 14 and pos.y() >= target_rect.bottom() - 14




