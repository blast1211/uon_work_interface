from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import random
import sys

from PySide6.QtCore import QObject, QPoint, QSettings, QThread, QTimer, Qt, Signal, Slot, QEvent, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontDatabase, QKeySequence, QPainter, QPen, QPixmap, QRegion, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
)

from attendance_widget.automation import AttendanceAutomation, AttendanceError, AttendanceSnapshot
from attendance_widget.calculations import normalize_times, target_minutes_for_label, week_date_strings, worked_minutes
from attendance_widget.chat import ChatConfig, LanChatClient
from attendance_widget.config import load_settings


def _discover_asset_root() -> Path:
    source_root = Path(__file__).resolve().parents[3]
    candidates: list[Path] = []

    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        meipass_path = Path(meipass)
        candidates.extend([meipass_path / "assets", meipass_path])

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir / "assets", exe_dir])

    candidates.extend([source_root / "assets", source_root])

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "koverwatch.ttf").exists():
            return resolved
    return source_root


ASSET_ROOT = _discover_asset_root()
FONT_PATH = ASSET_ROOT / "koverwatch.ttf"
BLUE_PATH = ASSET_ROOT / "occupation_blue.png"
RED_PATH  = ASSET_ROOT / "occupation_red.png"
HOG_THUMB_PATH = ASSET_ROOT / "hog_thumb.png"
THUMBNAIL_DIR = ASSET_ROOT / "thumbnail"
HP_ICON_PATH = ASSET_ROOT / "HP.png"
Q_SKILL_PATH = ASSET_ROOT / "Q_skill.png"
HOG_SKILL_PATH = ASSET_ROOT / "hog_skill.png"
HOG_GUN_PATH = ASSET_ROOT / "hog_gun.png"
BACK_ICON_PATH = ASSET_ROOT / "back.png"
TAB_BG_IMG_PATH = ASSET_ROOT / "tab_bg_img.png"
DAY_NAMES = ["월", "화", "수", "목", "금"]
REFRESH_INTERVAL_MS = 10_000
SETTINGS_ORG = "Chansol"
SETTINGS_APP = "AttendanceWidget"
BASE_UI_WIDTH = 1920
BASE_UI_HEIGHT = 1080


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


class WeeklyOvertimeRow(QFrame):
    def __init__(self, font_family: str, ui_scale: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.font_family = font_family
        self.ui_scale = ui_scale
        self.balance_minutes = 0
        self.max_minutes = 1
        self.setMinimumHeight(max(40, int(round(54 * self.ui_scale))))
        self.setStyleSheet("QFrame { background: transparent; border: none; }")

        self.base_panel = QFrame(self)
        self.base_panel.setStyleSheet("QFrame { background: rgba(8, 18, 28, 220); border: none; }")

        self.fill_panel = QFrame(self.base_panel)
        self.fill_panel.setStyleSheet("QFrame { background: rgba(47, 166, 255, 210); border: none; }")

        self.content = QWidget(self.base_panel)
        self.content.setAttribute(Qt.WA_TranslucentBackground)
        layout = QHBoxLayout(self.content)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(20)

        self.day_label = QLabel(self.content)
        self.balance_label = QLabel(self.content)
        self.come_label = QLabel(self.content)
        self.leave_label = QLabel(self.content)

        for label, width, alignment in (
            (self.day_label, int(round(110 * self.ui_scale)), Qt.AlignLeft | Qt.AlignVCenter),
            (self.balance_label, int(round(190 * self.ui_scale)), Qt.AlignLeft | Qt.AlignVCenter),
            (self.come_label, int(round(150 * self.ui_scale)), Qt.AlignLeft | Qt.AlignVCenter),
            (self.leave_label, int(round(150 * self.ui_scale)), Qt.AlignLeft | Qt.AlignVCenter),
        ):
            label.setMinimumWidth(width)
            label.setAlignment(alignment)
            label.setStyleSheet(
                f"color: rgba(245,250,255,0.96); font-family: '{self.font_family}'; font-size: {max(14, int(round(22 * self.ui_scale)))}px; background: transparent;"
            )
            layout.addWidget(label, 1)

        self.balance_label.setStyleSheet(
            f"color: rgba(245,250,255,0.96); font-family: '{self.font_family}'; font-size: {max(14, int(round(22 * self.ui_scale)))}px; background: transparent;"
        )

    def resizeEvent(self, event) -> None:
        self.base_panel.setGeometry(self.rect())
        self.content.setGeometry(self.base_panel.rect())
        self._update_fill()
        super().resizeEvent(event)

    def set_row_data(self, day_name: str, balance_minutes: int, come_time: str, leave_time: str, max_minutes: int) -> None:
        self.balance_minutes = balance_minutes
        self.max_minutes = max(max_minutes, 1)
        self.day_label.setText(day_name)
        self.balance_label.setText(self._format_balance(balance_minutes))
        self.come_label.setText(come_time)
        self.leave_label.setText(leave_time)

        if balance_minutes >= 0:
            fill_color = 'rgba(170, 34, 55, 215)'
            balance_color = '#ff8f98'
        else:
            fill_color = 'rgba(18, 122, 178, 215)'
            balance_color = '#7aeaff'

        self.fill_panel.setStyleSheet(f"QFrame {{ background: {fill_color}; border: none; }}")
        self.balance_label.setStyleSheet(
            f"color: {balance_color}; font-family: '{self.font_family}'; font-size: {max(14, int(round(22 * self.ui_scale)))}px; background: transparent;"
        )
        self._update_fill()

    def _update_fill(self) -> None:
        ratio = min(1.0, abs(self.balance_minutes) / max(self.max_minutes, 1))
        fill_width = int(self.base_panel.width() * ratio)
        self.fill_panel.setGeometry(0, 0, fill_width, self.base_panel.height())

    @staticmethod
    def _format_balance(minutes: int) -> str:
        sign = '+' if minutes >= 0 else '-'
        hours, remain = divmod(abs(minutes), 60)
        return f"{sign}{hours}:{remain:02d}"


class WeeklyOvertimeTable(QFrame):
    DAY_ORDER = {name: index for index, name in enumerate(DAY_NAMES)}

    def __init__(self, font_family: str, ui_scale: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.font_family = font_family
        self.ui_scale = ui_scale
        self.rows_data: list[dict[str, object]] = []
        self.sort_key = 'day'
        self.setStyleSheet("QFrame { background: transparent; border: none; }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(max(4, int(round(6 * self.ui_scale))))

        self.header = QFrame(self)
        self.header.setStyleSheet("QFrame { background: rgba(255,255,255,0.96); border: none; }")
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(int(round(18 * self.ui_scale)), int(round(10 * self.ui_scale)), int(round(18 * self.ui_scale)), int(round(10 * self.ui_scale)))
        header_layout.setSpacing(int(round(20 * self.ui_scale)))

        self.header_buttons: dict[str, QPushButton] = {}
        for key, title, width, alignment in (
            ('day', '요일', 110, Qt.AlignLeft | Qt.AlignVCenter),
            ('balance', '초과근무시간', 190, Qt.AlignLeft | Qt.AlignVCenter),
            ('come', '출근시간', 150, Qt.AlignLeft | Qt.AlignVCenter),
            ('leave', '퇴근시간', 150, Qt.AlignLeft | Qt.AlignVCenter),
        ):
            button = QPushButton(title, self.header)
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumWidth(int(round(width * self.ui_scale)))
            button.setStyleSheet(
                f"QPushButton {{ color: #16212c; font-family: '{self.font_family}'; font-size: {max(14, int(round(22 * self.ui_scale)))}px; background: transparent; border: none; text-align: left; padding: 0px; }}"
                "QPushButton:hover { color: #0a7f95; }"
            )
            button.clicked.connect(lambda checked=False, sort_key=key: self.set_sort(sort_key))
            header_layout.addWidget(button, 1, alignment)
            self.header_buttons[key] = button
        outer.addWidget(self.header)

        self.rows_container = QWidget(self)
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(max(2, int(round(4 * self.ui_scale))))
        outer.addWidget(self.rows_container)

        self.row_widgets = [WeeklyOvertimeRow(font_family, self.ui_scale, self.rows_container) for _ in DAY_NAMES]
        for row in self.row_widgets:
            self.rows_layout.addWidget(row)

        self._refresh_header_styles()

    def set_rows(self, rows: list[dict[str, object]]) -> None:
        self.rows_data = list(rows)
        self._apply_rows()

    def set_sort(self, sort_key: str) -> None:
        self.sort_key = sort_key
        self._refresh_header_styles()
        self._apply_rows()

    def _refresh_header_styles(self) -> None:
        titles = {
            'day': '요일',
            'balance': '초과근무시간',
            'come': '출근시간',
            'leave': '퇴근시간',
        }
        for key, button in self.header_buttons.items():
            marker = ' v' if key == self.sort_key else ''
            button.setText(f"{titles[key]}{marker}")

    def _apply_rows(self) -> None:
        rows = sorted(self.rows_data, key=self._sort_value_for_row)
        max_minutes = max((abs(int(row['balance_minutes'])) for row in rows), default=1)
        max_minutes = max(max_minutes, 1)
        for widget, row in zip(self.row_widgets, rows):
            widget.set_row_data(
                str(row['day_name']),
                int(row['balance_minutes']),
                str(row['come_time']),
                str(row['leave_time']),
                max_minutes,
            )
            widget.show()
        for widget in self.row_widgets[len(rows):]:
            widget.hide()

    def _sort_value_for_row(self, row: dict[str, object]):
        if self.sort_key == 'day':
            return self.DAY_ORDER.get(str(row['day_name']), 99)
        if self.sort_key == 'balance':
            return (-int(row['balance_minutes']), self.DAY_ORDER.get(str(row['day_name']), 99))
        if self.sort_key == 'come':
            return (-self._time_to_minutes(str(row['come_time'])), self.DAY_ORDER.get(str(row['day_name']), 99))
        if self.sort_key == 'leave':
            return (-self._time_to_minutes(str(row['leave_time'])), self.DAY_ORDER.get(str(row['day_name']), 99))
        return self.DAY_ORDER.get(str(row['day_name']), 99)

    @staticmethod
    def _time_to_minutes(text: str) -> int:
        if text == '--:--' or ':' not in text:
            return -1
        hour_text, minute_text = text.split(':', 1)
        try:
            return int(hour_text) * 60 + int(minute_text)
        except ValueError:
            return -1


class ChatInputBox(QPlainTextEdit):
    send_requested = Signal(str)
    dismissed = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Tab:
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if event.modifiers() & Qt.ShiftModifier:
                super().keyPressEvent(event)
                return
            text = self.toPlainText().strip()
            if text:
                self.send_requested.emit(text)
                self.clear()
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.dismissed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class CollapsibleSection(QFrame):
    toggled = Signal(bool)

    def __init__(self, title: str, font_family: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.title = title
        self.font_family = font_family
        self.expanded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.header = QFrame(self)
        self.header.setCursor(Qt.PointingHandCursor)
        self.header.setStyleSheet(
            "QFrame { background: white; border: 1px solid rgba(24,36,54,0.16); border-radius: 8px; }"
            "QFrame:hover { background: #f4f7fb; }"
        )
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(8)

        self.title_label = QLabel(title, self.header)
        self.title_label.setStyleSheet(
            f"color: #1a2533; background: transparent; font-family: '{self.font_family}'; font-size: 14px;"
        )
        header_layout.addWidget(self.title_label, 1)

        self.indicator_label = QLabel("v", self.header)
        self.indicator_label.setAlignment(Qt.AlignCenter)
        self.indicator_label.setFixedWidth(18)
        self.indicator_label.setStyleSheet(
            f"color: #1a2533; background: transparent; font-family: '{self.font_family}'; font-size: 14px;"
        )
        header_layout.addWidget(self.indicator_label)

        layout.addWidget(self.header)

        self.content = QFrame(self)
        self.content.setVisible(False)
        self.content.setStyleSheet("QFrame { background: transparent; border: none; }")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(6, 2, 6, 0)
        self.content_layout.setSpacing(10)
        layout.addWidget(self.content)

        self.header.mousePressEvent = self._handle_header_click
        self.title_label.mousePressEvent = self._handle_header_click
        self.indicator_label.mousePressEvent = self._handle_header_click

    def _handle_header_click(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.set_expanded(not self.expanded)
            event.accept()

    def mousePressEvent(self, event) -> None:
        if self.header.geometry().contains(event.position().toPoint()) and event.button() == Qt.LeftButton:
            self.set_expanded(not self.expanded)
            event.accept()
            return
        super().mousePressEvent(event)

    def add_widget(self, widget: QWidget, stretch: int = 0, alignment: Qt.AlignmentFlag | None = None) -> None:
        if alignment is None:
            self.content_layout.addWidget(widget, stretch)
        else:
            self.content_layout.addWidget(widget, stretch, alignment)

    def add_layout(self, layout: QVBoxLayout | QHBoxLayout, stretch: int = 0) -> None:
        self.content_layout.addLayout(layout, stretch)

    def set_expanded(self, expanded: bool) -> None:
        self.expanded = expanded
        self.content.setVisible(expanded)
        self.indicator_label.setText("^" if expanded else "v")
        self.toggled.emit(expanded)


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
        self.resolution_scale = self._calculate_resolution_scale()
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
        self.chat_client: LanChatClient | None = None
        self.chat_connected = False
        self.chat_presence_announced = False
        self.chat_drag_origin: QPoint | None = None
        self.chat_panel_pos_override: QPoint | None = None
        self.chat_resize_origin: QPoint | None = None
        self.chat_resize_start_geometry = None
        self.chat_resize_edges: str = ""
        self.chat_preview_mode = False
        self.chat_preview_timers: dict[int, tuple[QListWidgetItem, QTimer]] = {}
        self.chat_users: dict[str, dict[str, str]] = {}
        self.selected_thumbnail_name = ""
        self.thumbnail_pixmaps: dict[str, QPixmap] = {}
        self.chat_roster_visible = False
        self.chat_roster_target_visible = False
        self.chat_font_family = "Malgun Gothic"
        self.chat_metrics = {
            "panel_width": 430,
            "panel_height": 300,
            "panel_left": 34,
            "panel_anchor_y": 0,
            "title_font_size": 20,
            "meta_font_size": 13,
            "message_font_size": 16,
            "input_font_size": 16,
            "input_height": 82,
            "list_spacing": 4,
            "panel_gap": 12,
            "history_radius": 18,
            "input_radius": 14,
            "history_padding_left": 14,
            "history_padding_top": 12,
            "history_padding_right": 10,
            "history_padding_bottom": 12,
            "input_padding_left": 12,
            "input_padding_top": 8,
            "input_padding_right": 12,
            "input_padding_bottom": 8,
            "input_text_padding_x": 8,
            "input_text_padding_y": 6,
            "scrollbar_width": 14,
            "scrollbar_margin_top": 10,
            "scrollbar_margin_right": 4,
            "scrollbar_margin_bottom": 10,
            "scrollbar_radius": 8,
            "scrollbar_handle_min_height": 44,
            "notice_width": 420,
            "notice_height": 74,
            "notice_left": 34,
            "notice_gap": 14,
            "roster_slot_size": 92,
            "roster_back_scale": 2.2,
            "roster_back_offset_y": -120,
            "roster_avatar_scale": 2.2,
            "roster_avatar_offset_x": 0,
            "roster_avatar_offset_y": 15,
            "roster_fade_in_ms": 180,
            "roster_fade_out_ms": 140,
            "roster_name_font_size": 35,
            "roster_name_italic": 1,
            "roster_name_bold": 0,
        }
        self.card_metrics = {
            "image_scale": 0.5,
            "text_left_x": 85,
            "text_y": 20,
            "text_left_width": 150,
            "text_right_x_offset": 225,
            "text_right_width": 126,
            "text_height": 72,
        }
        self.hud_metrics = {
            "left_thumb_padding_x": 36,
            "left_thumb_padding_y": 34,
            "left_thumb_scale": 0.1,
            "left_hp_padding_x": 0,
            "left_hp_padding_y": 90,
            "left_hp_gap": 14,
            "left_hp_scale": 0.08,
            "center_q_offset_x": 0,
            "center_q_padding_y": 30,
            "center_q_scale": 0.25,
            "right_skill_padding_x": 0,
            "right_skill_padding_y": 60,
            "right_skill_scale": 0.08,
            "right_gun_padding_x": 80,
            "right_gun_padding_y": 60,
            "right_gun_gap": 18,
            "right_gun_scale": 0.08,
        }
        self.settings_metrics = {
            "settings_title_font_size": 31,
            "tab_height": 38,
            "tab_font_size": 21,
            "section_title_font_size": 38,
            "section_subtitle_font_size": 17,
            "row_label_font_size": 25,
            "row_value_font_size": 22,
            "checkbox_font_size": 20,
            "button_font_size": 24,
            "action_button_font_size": 24,
            "field_font_size": 16,
            "username_field_font_size": 20,
            "password_field_font_size": 20,
            "status_font_size": 15,
            "hint_font_size": 18,
            "row_label_width": 120,
            "row_label_width_compact": 140,
            "input_height": 42,
            "input_width": 300,
            "single_button_width": 300,
            "action_button_min_width": 0,
            "tab_min_width": 20,
            "tab_width": 100,
            "chat_row_label_width": 160,
        }
        self._load_assets()
        self._build_worker()
        self._build_ui()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self._build_timer()
        self._load_saved_preferences()
        self._update_score_card(0)
        self._set_logged_in_ui(False)

    def _calculate_resolution_scale(self) -> float:
        screen = QApplication.primaryScreen()
        if screen is None:
            return 1.0
        available = screen.availableGeometry()
        width_scale = available.width() / BASE_UI_WIDTH
        height_scale = available.height() / BASE_UI_HEIGHT
        return max(0.65, min(width_scale, height_scale))

    def _scaled_metric(self, name: str, minimum: int = 1) -> int:
        return max(minimum, int(round(self.settings_metrics[name] * self.resolution_scale)))

    def _scaled_hud_metric(self, name: str) -> int:
        return int(round(self.hud_metrics[name] * self.resolution_scale))

    def _scaled_chat_metric(self, name: str, minimum: int = 0) -> int:
        return max(minimum, int(round(self.chat_metrics[name] * self.resolution_scale)))

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
        thumbnail_candidates: list[Path] = []
        if THUMBNAIL_DIR.exists() and THUMBNAIL_DIR.is_dir():
            for pattern in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                thumbnail_candidates.extend(sorted(THUMBNAIL_DIR.glob(pattern)))
        if not thumbnail_candidates and HOG_THUMB_PATH.exists():
            thumbnail_candidates.append(HOG_THUMB_PATH)
        self.thumbnail_pixmaps = {path.name: QPixmap(str(path)) for path in thumbnail_candidates}
        selected_thumbnail = random.choice(thumbnail_candidates) if thumbnail_candidates else HOG_THUMB_PATH
        self.selected_thumbnail_name = selected_thumbnail.name
        self.hog_thumb_pixmap = QPixmap(str(selected_thumbnail))
        self.hp_icon_pixmap = QPixmap(str(HP_ICON_PATH))
        self.q_skill_pixmap = QPixmap(str(Q_SKILL_PATH))
        self.hog_skill_pixmap = QPixmap(str(HOG_SKILL_PATH))
        self.hog_gun_pixmap = QPixmap(str(HOG_GUN_PATH))
        self.roster_back_pixmap = QPixmap(str(BACK_ICON_PATH))
        self.tab_bg_pixmap = QPixmap(str(TAB_BG_IMG_PATH))

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
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

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

        root.addWidget(self.card, alignment=Qt.AlignLeft | Qt.AlignTop)
        self._build_settings_window()
        self._build_chat_window()
        self._build_chat_roster_window()
        self._apply_card_geometry()
        self.adjustSize()

    def _build_settings_window(self) -> None:
        self.details_panel = QWidget(None)
        self.details_panel.setWindowTitle("근태 설정")
        self.details_panel.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.details_panel.setAttribute(Qt.WA_TranslucentBackground)

        outer = QVBoxLayout(self.details_panel)
        outer.setContentsMargins(22, 20, 22, 22)
        outer.setSpacing(0)

        self.settings_header = QWidget(self.details_panel)
        header_layout = QVBoxLayout(self.settings_header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        self.settings_title = QLabel("ATTENDANCE SETTINGS", self.settings_header)
        self.settings_title.setStyleSheet(
            f"color: rgba(234,242,255,0.85); font-family: '{self.font_family}'; font-size: {self._scaled_metric('settings_title_font_size')}px; letter-spacing: 1px; background: transparent;"
        )
        header_layout.addWidget(self.settings_title, alignment=Qt.AlignLeft)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(15)
        tab_row.setContentsMargins(0, 0, 0, 0)
        self.settings_tab_buttons: list[QPushButton] = []
        for index, title in enumerate(("세션", "요일별 근무", "환경 설정", "채팅")):
            button = QPushButton(title, self.settings_header)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda checked, idx=index: self._switch_settings_tab(idx))
            button.setFixedHeight(self._scaled_metric("tab_height"))
            if self.settings_metrics["tab_width"] > 0:
                button.setFixedWidth(self._scaled_metric("tab_width"))
            elif self.settings_metrics["tab_min_width"] > 0:
                button.setMinimumWidth(self._scaled_metric("tab_min_width"))
            self.settings_tab_buttons.append(button)
            tab_row.addWidget(button)
        tab_row.addStretch(1)
        header_layout.addLayout(tab_row)
        outer.addWidget(self.settings_header, alignment=Qt.AlignLeft | Qt.AlignTop)

        outer.addStretch(1)

        center_row = QHBoxLayout()
        center_row.setContentsMargins(0, 0, 0, 0)
        center_row.setSpacing(0)
        center_row.addStretch(1)

        self.settings_stack = QStackedWidget(self.details_panel)
        self.settings_stack.setStyleSheet("QStackedWidget { background: transparent; }")
        center_row.addWidget(self.settings_stack, alignment=Qt.AlignCenter)
        center_row.addStretch(1)
        outer.addLayout(center_row, 1)

        outer.addStretch(1)

        self.left_hud_thumb = QLabel(self.details_panel)
        self.left_hud_thumb.setAttribute(Qt.WA_TranslucentBackground)
        self.left_hud_thumb.setScaledContents(True)
        self.left_hud_hp = QLabel(self.details_panel)
        self.left_hud_hp.setAttribute(Qt.WA_TranslucentBackground)
        self.left_hud_hp.setScaledContents(True)
        self.center_hud_q = QLabel(self.details_panel)
        self.center_hud_q.setAttribute(Qt.WA_TranslucentBackground)
        self.center_hud_q.setScaledContents(True)
        self.right_hud_skill = QLabel(self.details_panel)
        self.right_hud_skill.setAttribute(Qt.WA_TranslucentBackground)
        self.right_hud_skill.setScaledContents(True)
        self.right_hud_gun = QLabel(self.details_panel)
        self.right_hud_gun.setAttribute(Qt.WA_TranslucentBackground)
        self.right_hud_gun.setScaledContents(True)

        self.settings_cards: list[QFrame] = []

        session_page = QWidget()
        session_page_layout = QVBoxLayout(session_page)
        session_page_layout.setContentsMargins(0, 0, 0, 0)
        session_page_layout.setSpacing(0)
        session_card, session_card_layout = self._create_settings_card("세션 관리", "로그인과 출퇴근 제어")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("사내 계정")
        self.username_input.setMinimumHeight(self._scaled_metric("input_height"))
        if self.settings_metrics["input_width"] > 0:
            self.username_input.setFixedWidth(self._scaled_metric("input_width"))
        self.username_input.setStyleSheet(self._field_style("username_field_font_size"))
        self.username_input.textChanged.connect(self._sync_chat_identity_field)
        self._add_setting_row(session_card_layout, "아이디", self.username_input)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("비밀번호")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMinimumHeight(self._scaled_metric("input_height"))
        if self.settings_metrics["input_width"] > 0:
            self.password_input.setFixedWidth(self._scaled_metric("input_width"))
        self.password_input.setStyleSheet(self._field_style("password_field_font_size"))
        self._add_setting_row(session_card_layout, "비밀번호", self.password_input)

        self.login_button = QPushButton("접속")
        self.login_button.setFixedHeight(self._scaled_metric("input_height"))
        if self.settings_metrics["single_button_width"] > 0:
            self.login_button.setFixedWidth(self._scaled_metric("single_button_width"))
        self.login_button.clicked.connect(self.login_to_site)
        self.login_button.setStyleSheet(self._accent_button_style())
        self._add_setting_row(session_card_layout, "로그인", self.login_button)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.refresh_button = QPushButton("새로고침")
        self.work_in_button = QPushButton("출근")
        self.work_out_button = QPushButton("퇴근")
        self.exit_button = QPushButton("종료")
        for button in (self.refresh_button, self.work_in_button, self.work_out_button, self.exit_button):
            button.setFixedHeight(max(32, int(round(40 * self.resolution_scale))))
            if self.settings_metrics["action_button_min_width"] > 0:
                button.setMinimumWidth(self._scaled_metric("action_button_min_width"))
            button.setStyleSheet(self._action_button_style())

        self.work_in_time_label = QLabel("")
        self.work_in_time_label.setAlignment(Qt.AlignCenter)
        self.work_in_time_label.setStyleSheet(
            f"color: #48d9ff; background: transparent; font-family: '{self.font_family}'; font-size: {self.settings_metrics['hint_font_size']}px;"
        )
        self.work_out_time_label = QLabel("")
        self.work_out_time_label.setAlignment(Qt.AlignCenter)
        self.work_out_time_label.setStyleSheet(
            f"color: #ff6a6a; background: transparent; font-family: '{self.font_family}'; font-size: {self.settings_metrics['hint_font_size']}px;"
        )

        refresh_col = QVBoxLayout()
        refresh_col.setSpacing(6)
        refresh_col.addWidget(self.refresh_button)
        refresh_col.addWidget(QLabel(""))
        action_row.addLayout(refresh_col)

        work_in_col = QVBoxLayout()
        work_in_col.setSpacing(6)
        work_in_col.addWidget(self.work_in_button)
        work_in_col.addWidget(self.work_in_time_label)
        action_row.addLayout(work_in_col)

        work_out_col = QVBoxLayout()
        work_out_col.setSpacing(6)
        work_out_col.addWidget(self.work_out_button)
        work_out_col.addWidget(self.work_out_time_label)
        action_row.addLayout(work_out_col)

        exit_col = QVBoxLayout()
        exit_col.setSpacing(6)
        exit_col.addWidget(self.exit_button)
        exit_col.addWidget(QLabel(""))
        action_row.addLayout(exit_col)

        self.refresh_button.clicked.connect(self.refresh_snapshot)
        self.work_in_button.clicked.connect(self.work_in)
        self.work_out_button.clicked.connect(self.work_out)
        self.exit_button.clicked.connect(self.close_and_exit)
        self._add_setting_row(session_card_layout, "출퇴근 제어", action_row)

        self.login_spinner = QProgressBar(session_card)
        self.login_spinner.setRange(0, 0)
        self.login_spinner.setTextVisible(False)
        self.login_spinner.setFixedHeight(8)
        self.login_spinner.setVisible(False)
        self.login_spinner.setStyleSheet(
            "QProgressBar { background: rgba(255,255,255,0.08); border: none; }"
            "QProgressBar::chunk { background: #36e0ff; }"
        )
        self._add_setting_row(session_card_layout, "진행 상태", self.login_spinner)

        self.status_label = QLabel("접속하면 숨겨진 브라우저 세션이 시작됩니다.")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            f"color: rgba(232,240,255,0.82); font-family: '{self.font_family}'; font-size: {self.settings_metrics['status_font_size']}px; background: transparent;"
        )
        self._add_setting_row(session_card_layout, "안내", self.status_label)

        session_page_layout.addWidget(session_card, alignment=Qt.AlignCenter)
        self.settings_stack.addWidget(session_page)

        work_page = QWidget()
        work_page_layout = QVBoxLayout(work_page)
        work_page_layout.setContentsMargins(0, 0, 0, 0)
        work_page_layout.setSpacing(0)
        work_card, work_card_layout = self._create_settings_card("요일별 초과근무", "주간 근무 현황을 확인합니다")
        self.weekly_table = WeeklyOvertimeTable(self.font_family, self.resolution_scale, work_card)
        work_card_layout.addWidget(self.weekly_table)
        work_page_layout.addWidget(work_card, alignment=Qt.AlignCenter)
        self.settings_stack.addWidget(work_page)

        options_page = QWidget()
        options_page_layout = QVBoxLayout(options_page)
        options_page_layout.setContentsMargins(0, 0, 0, 0)
        options_page_layout.setSpacing(0)
        options_card, options_card_layout = self._create_settings_card("환경 설정", "위젯 표시 방식과 갱신 주기")

        self.headless_checkbox = QCheckBox("크롬 헤드리스")
        self.always_on_top_checkbox = QCheckBox("항상 위에 표시")
        for checkbox in (self.headless_checkbox, self.always_on_top_checkbox):
            checkbox.setStyleSheet(self._settings_checkbox_style())
        self.headless_checkbox.toggled.connect(self._on_headless_toggled)
        self.always_on_top_checkbox.toggled.connect(self._on_always_on_top_toggled)
        self._add_setting_row(options_card_layout, "브라우저", self.headless_checkbox)
        self._add_setting_row(options_card_layout, "윈도우", self.always_on_top_checkbox)

        card_opacity_row = QHBoxLayout()
        card_opacity_row.setSpacing(12)
        self.card_opacity_slider = QSlider(Qt.Horizontal)
        self.card_opacity_slider.setRange(10, 90)
        self.card_opacity_slider.valueChanged.connect(self._on_card_opacity_changed)
        self.card_opacity_slider.setStyleSheet(self._slider_style())
        self.card_opacity_slider.setMinimumHeight(26)
        self.card_opacity_value_label = QLabel("50%")
        self.card_opacity_value_label.setStyleSheet(self._settings_value_style())
        card_opacity_row.addWidget(self.card_opacity_slider, 1)
        card_opacity_row.addWidget(self.card_opacity_value_label)
        self._add_setting_row(options_card_layout, "초과근무 UI 투명도", card_opacity_row)

        ui_opacity_row = QHBoxLayout()
        ui_opacity_row.setSpacing(12)
        self.ui_opacity_slider = QSlider(Qt.Horizontal)
        self.ui_opacity_slider.setRange(10, 90)
        self.ui_opacity_slider.valueChanged.connect(self._on_ui_opacity_changed)
        self.ui_opacity_slider.setStyleSheet(self._slider_style())
        self.ui_opacity_slider.setMinimumHeight(26)
        self.ui_opacity_value_label = QLabel("50%")
        self.ui_opacity_value_label.setStyleSheet(self._settings_value_style())
        ui_opacity_row.addWidget(self.ui_opacity_slider, 1)
        ui_opacity_row.addWidget(self.ui_opacity_value_label)
        self._add_setting_row(options_card_layout, "설정창 투명도", ui_opacity_row)

        refresh_row = QHBoxLayout()
        refresh_row.setSpacing(12)
        self.refresh_interval_slider = QSlider(Qt.Horizontal)
        self.refresh_interval_slider.setRange(10, 300)
        self.refresh_interval_slider.valueChanged.connect(self._on_refresh_interval_changed)
        self.refresh_interval_slider.setStyleSheet(self._slider_style())
        self.refresh_interval_slider.setMinimumHeight(26)
        self.refresh_interval_value_label = QLabel("10초")
        self.refresh_interval_value_label.setStyleSheet(self._settings_value_style())
        refresh_row.addWidget(self.refresh_interval_slider, 1)
        refresh_row.addWidget(self.refresh_interval_value_label)
        self._add_setting_row(options_card_layout, "새로고침 주기", refresh_row)

        options_hint = QLabel("더블클릭으로 설정창을 열고 닫을 수 있습니다.")
        options_hint.setWordWrap(True)
        options_hint.setStyleSheet(
            f"color: rgba(232,240,255,0.68); font-family: '{self.font_family}'; font-size: {self._scaled_metric('hint_font_size')}px; background: transparent;"
        )
        self._add_setting_row(options_card_layout, "도움말", options_hint)

        options_page_layout.addWidget(options_card, alignment=Qt.AlignCenter)
        self.settings_stack.addWidget(options_page)

        chat_page = QWidget()
        chat_page_layout = QVBoxLayout(chat_page)
        chat_page_layout.setContentsMargins(0, 0, 0, 0)
        chat_page_layout.setSpacing(0)
        chat_card, chat_card_layout = self._create_settings_card("LAN 채팅", "같은 네트워크 안에서 자동으로 연결됩니다")

        self.chat_enabled_checkbox = QCheckBox("로그인 시 자동 접속")
        self.chat_enabled_checkbox.setStyleSheet(self._settings_checkbox_style())
        self.chat_enabled_checkbox.toggled.connect(self._on_chat_enabled_toggled)
        self._add_setting_row(chat_card_layout, "채팅 사용", self.chat_enabled_checkbox, label_width=self.settings_metrics["chat_row_label_width"])

        self.chat_system_checkbox = QCheckBox("입장/퇴장 메시지 표시")
        self.chat_system_checkbox.setStyleSheet(self._settings_checkbox_style())
        self.chat_system_checkbox.toggled.connect(self._on_chat_system_messages_toggled)
        self._add_setting_row(chat_card_layout, "시스템 메시지", self.chat_system_checkbox, label_width=self.settings_metrics["chat_row_label_width"])

        self.chat_nickname_input = QLineEdit()
        self.chat_nickname_input.setPlaceholderText("로그인 아이디와 동일")
        self.chat_nickname_input.setReadOnly(True)
        self.chat_nickname_input.setFocusPolicy(Qt.NoFocus)
        self.chat_nickname_input.setMinimumHeight(self._scaled_metric("input_height"))
        self.chat_nickname_input.setFixedWidth(self._scaled_metric("input_width"))
        self.chat_nickname_input.setStyleSheet(self._field_style())
        self._add_setting_row(chat_card_layout, "채팅 ID", self.chat_nickname_input, label_width=self.settings_metrics["chat_row_label_width"])

        self.chat_room_input = QLineEdit()
        self.chat_room_input.setPlaceholderText("attendance-room")
        self.chat_room_input.setMinimumHeight(self._scaled_metric("input_height"))
        self.chat_room_input.setFixedWidth(self._scaled_metric("input_width"))
        self.chat_room_input.setStyleSheet(self._field_style())
        self.chat_room_input.editingFinished.connect(self._on_chat_settings_edited)
        self._add_setting_row(chat_card_layout, "채팅방 이름", self.chat_room_input, label_width=self.settings_metrics["chat_row_label_width"])

        self.chat_group_input = QLineEdit()
        self.chat_group_input.setPlaceholderText("239.255.42.99")
        self.chat_group_input.setMinimumHeight(self._scaled_metric("input_height"))
        self.chat_group_input.setFixedWidth(self._scaled_metric("input_width"))
        self.chat_group_input.setStyleSheet(self._field_style())
        self.chat_group_input.editingFinished.connect(self._on_chat_settings_edited)
        self._add_setting_row(chat_card_layout, "멀티캐스트 그룹", self.chat_group_input, label_width=self.settings_metrics["chat_row_label_width"])

        self.chat_port_input = QLineEdit()
        self.chat_port_input.setPlaceholderText("45454")
        self.chat_port_input.setMinimumHeight(self._scaled_metric("input_height"))
        self.chat_port_input.setFixedWidth(self._scaled_metric("single_button_width"))
        self.chat_port_input.setStyleSheet(self._field_style())
        self.chat_port_input.editingFinished.connect(self._on_chat_settings_edited)
        self._add_setting_row(chat_card_layout, "포트", self.chat_port_input, label_width=self.settings_metrics["chat_row_label_width"])

        chat_opacity_row = QHBoxLayout()
        chat_opacity_row.setSpacing(12)
        self.chat_opacity_slider = QSlider(Qt.Horizontal)
        self.chat_opacity_slider.setRange(20, 100)
        self.chat_opacity_slider.valueChanged.connect(self._on_chat_opacity_changed)
        self.chat_opacity_slider.setStyleSheet(self._slider_style())
        self.chat_opacity_slider.setMinimumHeight(26)
        self.chat_opacity_value_label = QLabel("100%")
        self.chat_opacity_value_label.setStyleSheet(self._settings_value_style())
        chat_opacity_row.addWidget(self.chat_opacity_slider, 1)
        chat_opacity_row.addWidget(self.chat_opacity_value_label)
        self._add_setting_row(chat_card_layout, "채팅창 투명도", chat_opacity_row, label_width=self.settings_metrics["chat_row_label_width"])

        chat_font_row = QHBoxLayout()
        chat_font_row.setSpacing(12)
        self.chat_font_size_slider = QSlider(Qt.Horizontal)
        self.chat_font_size_slider.setRange(10, 32)
        self.chat_font_size_slider.valueChanged.connect(self._on_chat_font_size_changed)
        self.chat_font_size_slider.setStyleSheet(self._slider_style())
        self.chat_font_size_slider.setMinimumHeight(26)
        self.chat_font_size_value_label = QLabel("16px")
        self.chat_font_size_value_label.setStyleSheet(self._settings_value_style())
        chat_font_row.addWidget(self.chat_font_size_slider, 1)
        chat_font_row.addWidget(self.chat_font_size_value_label)
        self._add_setting_row(chat_card_layout, "채팅 폰트 크기", chat_font_row, label_width=self.settings_metrics["chat_row_label_width"])

        chat_hide_row = QHBoxLayout()
        chat_hide_row.setSpacing(12)
        self.chat_hide_slider = QSlider(Qt.Horizontal)
        self.chat_hide_slider.setRange(3, 30)
        self.chat_hide_slider.valueChanged.connect(self._on_chat_hide_seconds_changed)
        self.chat_hide_slider.setStyleSheet(self._slider_style())
        self.chat_hide_slider.setMinimumHeight(26)
        self.chat_hide_value_label = QLabel("8초")
        self.chat_hide_value_label.setStyleSheet(self._settings_value_style())
        chat_hide_row.addWidget(self.chat_hide_slider, 1)
        chat_hide_row.addWidget(self.chat_hide_value_label)
        self._add_setting_row(chat_card_layout, "자동 숨김", chat_hide_row, label_width=self.settings_metrics["chat_row_label_width"])

        self.chat_reconnect_button = QPushButton("채팅 다시 연결")
        self.chat_reconnect_button.setFixedHeight(self._scaled_metric("input_height"))
        self.chat_reconnect_button.setFixedWidth(self._scaled_metric("single_button_width"))
        self.chat_reconnect_button.setStyleSheet(self._action_button_style())
        self.chat_reconnect_button.clicked.connect(self._reconnect_chat)
        self._add_setting_row(chat_card_layout, "연결 제어", self.chat_reconnect_button, label_width=self.settings_metrics["chat_row_label_width"])

        chat_page_layout.addWidget(chat_card, alignment=Qt.AlignCenter)
        self.settings_stack.addWidget(chat_page)

        self._resize_settings_window()
        self._switch_settings_tab(0)
        self.details_panel.hide()

    def _build_chat_window(self) -> None:
        self.chat_panel = QWidget(None)
        self.chat_panel.setWindowTitle("LAN 채팅")
        self.chat_panel.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.chat_panel.setAttribute(Qt.WA_TranslucentBackground)

        root = QVBoxLayout(self.chat_panel)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        shell_radius = max(12, int(round(self.chat_metrics["history_radius"] * self.resolution_scale)))
        panel_radius = max(10, int(round(self.chat_metrics["input_radius"] * self.resolution_scale)))
        shell_layout_gap = max(6, int(round(self.chat_metrics["panel_gap"] * self.resolution_scale)))
        shared_panel_background = "rgba(14, 21, 34, 222)"
        shared_panel_border = "rgba(118, 169, 214, 0.20)"
        scroll_handle_radius = max(4, int(round(self.chat_metrics["scrollbar_radius"] * self.resolution_scale)))
        chat_scrollbar_style = (
            "QScrollBar:vertical {"
            " background: transparent;"
            f" width: {max(8, int(round(self.chat_metrics['scrollbar_width'] * self.resolution_scale)))}px;"
            f" margin: {max(0, int(round(self.chat_metrics['scrollbar_margin_top'] * self.resolution_scale)))}px {max(0, int(round(self.chat_metrics['scrollbar_margin_right'] * self.resolution_scale)))}px {max(0, int(round(self.chat_metrics['scrollbar_margin_bottom'] * self.resolution_scale)))}px 0px;"
            " border: none;"
            "}"
            "QScrollBar::handle:vertical {"
            " background: rgba(245, 248, 255, 0.78);"
            f" border-radius: {scroll_handle_radius}px;"
            f" min-height: {max(24, int(round(self.chat_metrics['scrollbar_handle_min_height'] * self.resolution_scale)))}px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            " height: 0px;"
            " background: transparent;"
            " border: none;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            " background: transparent;"
            "}"
        )

        self.chat_shell = QFrame(self.chat_panel)
        self.chat_shell.mousePressEvent = self._chat_mouse_press_event
        self.chat_shell.mouseMoveEvent = self._chat_mouse_move_event
        self.chat_shell.mouseReleaseEvent = self._chat_mouse_release_event
        self.chat_shell.setStyleSheet(
            "QFrame {"
            " background: transparent;"
            " border: none;"
            "}"
        )
        shell_layout = QVBoxLayout(self.chat_shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(shell_layout_gap)

        self.chat_history_frame_style = (
            "QFrame {"
            f" background: {shared_panel_background};"
            f" border: 1px solid {shared_panel_border};"
            f" border-radius: {shell_radius}px;"
            "}"
        )
        self.chat_history_preview_style = (
            "QFrame {"
            " background: transparent;"
            " border: none;"
            "}"
        )
        self.chat_history_frame = QFrame(self.chat_shell)
        self.chat_history_frame.mousePressEvent = self._chat_mouse_press_event
        self.chat_history_frame.mouseMoveEvent = self._chat_mouse_move_event
        self.chat_history_frame.mouseReleaseEvent = self._chat_mouse_release_event
        self.chat_history_frame.setStyleSheet(self.chat_history_frame_style)
        history_layout = QVBoxLayout(self.chat_history_frame)
        history_layout.setContentsMargins(
            self._scaled_chat_metric("history_padding_left"),
            self._scaled_chat_metric("history_padding_top"),
            self._scaled_chat_metric("history_padding_right"),
            self._scaled_chat_metric("history_padding_bottom"),
        )
        history_layout.setSpacing(8)

        self.chat_history = QListWidget(self.chat_history_frame)
        self.chat_history.mousePressEvent = self._chat_mouse_press_event
        self.chat_history.mouseMoveEvent = self._chat_mouse_move_event
        self.chat_history.mouseReleaseEvent = self._chat_mouse_release_event
        self.chat_history.setFocusPolicy(Qt.NoFocus)
        self.chat_history.setSelectionMode(QListWidget.NoSelection)
        self.chat_history.setWordWrap(True)
        self.chat_history.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_history.setTextElideMode(Qt.ElideNone)
        self.chat_history.setWrapping(False)
        self.chat_history.setStyleSheet(
            f"QListWidget {{ background: transparent; color: rgba(242,247,255,0.95); border: none; outline: none; font-family: '{self.chat_font_family}'; font-size: {max(12, int(round(self.chat_metrics['message_font_size'] * self.resolution_scale)))}px; padding-right: 4px; }}"
            "QListWidget::item { padding: 4px 2px; border: none; }"
            + chat_scrollbar_style
        )
        history_layout.addWidget(self.chat_history, 1)
        shell_layout.addWidget(self.chat_history_frame, 1)

        self.chat_input_frame = QFrame(self.chat_shell)
        self.chat_input_frame.setStyleSheet(
            "QFrame {"
            f" background: {shared_panel_background};"
            f" border: 1px solid {shared_panel_border};"
            f" border-radius: {panel_radius}px;"
            "}"
        )
        input_layout = QVBoxLayout(self.chat_input_frame)
        input_layout.setContentsMargins(
            self._scaled_chat_metric("input_padding_left"),
            self._scaled_chat_metric("input_padding_top"),
            self._scaled_chat_metric("input_padding_right"),
            self._scaled_chat_metric("input_padding_bottom"),
        )
        input_layout.setSpacing(6)

        self.chat_input = ChatInputBox(self.chat_input_frame)
        self.chat_input.setPlaceholderText("메시지를 입력하세요. Enter 전송 / Shift+Enter 줄바꿈 / Esc 닫기")
        self.chat_input.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.chat_input.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chat_input.setFixedHeight(max(52, int(round(self.chat_metrics['input_height'] * self.resolution_scale))))
        self.chat_input.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; color: #f3f8ff; border: none; padding: {self._scaled_chat_metric('input_text_padding_y')}px {self._scaled_chat_metric('input_text_padding_x')}px; font-family: '{self.chat_font_family}'; font-size: {max(12, int(round(self.chat_metrics['input_font_size'] * self.resolution_scale)))}px; }}"
            f"QPlainTextEdit[placeholderText] {{ color: rgba(211,224,240,0.46); }}"
            + chat_scrollbar_style
        )
        self.chat_input.send_requested.connect(self._send_chat_message)
        self.chat_input.dismissed.connect(self._hide_chat_panel)
        input_layout.addWidget(self.chat_input)
        shell_layout.addWidget(self.chat_input_frame)

        self.chat_hint_label = QLabel("Shift+Enter 로 열기", self.chat_shell)
        self.chat_hint_label.setStyleSheet(
            f"color: rgba(232,240,255,0.48); font-family: '{self.chat_font_family}'; font-size: {max(10, int(round(self.chat_metrics['meta_font_size'] * self.resolution_scale)))}px; background: transparent;"
        )
        shell_layout.addWidget(self.chat_hint_label)

        self.chat_preview_spacer = QWidget(self.chat_shell)
        self.chat_preview_spacer.setFixedHeight(self.chat_input_frame.sizeHint().height() + self.chat_hint_label.sizeHint().height() + shell_layout.spacing())
        self.chat_preview_spacer.hide()
        shell_layout.addWidget(self.chat_preview_spacer)

        self.chat_preview_frame = QFrame(self.chat_shell)
        self.chat_preview_frame.mousePressEvent = self._chat_mouse_press_event
        self.chat_preview_frame.mouseMoveEvent = self._chat_mouse_move_event
        self.chat_preview_frame.mouseReleaseEvent = self._chat_mouse_release_event
        self.chat_preview_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        self.chat_preview_items: list[QFrame] = []
        self.chat_preview_layout = QVBoxLayout(self.chat_preview_frame)
        self.chat_preview_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_preview_layout.setSpacing(4)
        self.chat_preview_layout.addStretch(1)
        self.chat_preview_stack = QVBoxLayout()
        self.chat_preview_stack.setContentsMargins(0, 0, 0, 0)
        self.chat_preview_stack.setSpacing(4)
        self.chat_preview_layout.addLayout(self.chat_preview_stack)
        self.chat_preview_frame.hide()
        shell_layout.addWidget(self.chat_preview_frame, 1)

        root.addWidget(self.chat_shell)
        self.chat_panel.hide()

        self.chat_notice_panel = None

        self.chat_hide_timer = QTimer(self)
        self.chat_hide_timer.setSingleShot(True)
        self.chat_hide_timer.timeout.connect(self._hide_chat_panel_if_idle)

        self.chat_shortcut = QShortcut(QKeySequence("Shift+Return"), self)
        self.chat_shortcut.activated.connect(self._activate_chat_input)
        self.details_chat_shortcut = QShortcut(QKeySequence("Shift+Return"), self.details_panel)
        self.details_chat_shortcut.activated.connect(self._activate_chat_input)

        self._position_chat_window()
        self._position_chat_notice_window()

    def _chat_roster_name_style(self) -> str:
        font_size = self._scaled_chat_metric("roster_name_font_size", 10)
        font_style = "italic" if self.chat_metrics.get("roster_name_italic", 0) else "normal"
        font_weight = "700" if self.chat_metrics.get("roster_name_bold", 0) else "400"
        return (
            f"color: #39e6ff; background: transparent; font-family: '{self.font_family}'; "
            f"font-size: {font_size}px; font-style: {font_style}; font-weight: {font_weight};"
        )

    def _build_chat_roster_window(self) -> None:
        self.chat_roster_panel = QWidget(None)
        self.chat_roster_panel.setWindowTitle("채팅 접속자")
        self.chat_roster_panel.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.chat_roster_panel.setAttribute(Qt.WA_TranslucentBackground)
        self.chat_roster_opacity = QGraphicsOpacityEffect(self.chat_roster_panel)
        self.chat_roster_opacity.setOpacity(0.0)
        self.chat_roster_panel.setGraphicsEffect(self.chat_roster_opacity)
        self.chat_roster_fade_animation = QPropertyAnimation(self.chat_roster_opacity, b"opacity", self)
        self.chat_roster_fade_animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.chat_roster_fade_animation.finished.connect(self._on_chat_roster_fade_finished)

        outer = QVBoxLayout(self.chat_roster_panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.chat_roster_background = QLabel(self.chat_roster_panel)
        self.chat_roster_background.setScaledContents(True)
        self.chat_roster_background.lower()

        self.chat_roster_content = QWidget(self.chat_roster_panel)
        content_layout = QVBoxLayout(self.chat_roster_content)
        content_layout.setContentsMargins(48, 38, 48, 56)
        content_layout.setSpacing(0)
        content_layout.addStretch(1)

        self.chat_roster_rows_host = QWidget(self.chat_roster_content)
        self.chat_roster_rows_host.setStyleSheet("QWidget { background: transparent; border: none; }")
        self.chat_roster_rows_layout = QVBoxLayout(self.chat_roster_rows_host)
        self.chat_roster_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_roster_rows_layout.setSpacing(32)
        content_layout.addWidget(self.chat_roster_rows_host, 0, Qt.AlignCenter)
        content_layout.addStretch(1)

        self.chat_roster_row_widgets: list[QWidget] = []

        outer.addWidget(self.chat_roster_content)
        self.chat_roster_panel.hide()
        self._position_chat_roster_window()
        self._update_chat_roster_window()

    def _position_chat_roster_window(self) -> None:
        if not hasattr(self, "chat_roster_panel"):
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            self.chat_roster_panel.setGeometry(0, 0, 1280, 720)
            self.chat_roster_background.setGeometry(self.chat_roster_panel.rect())
            return
        available = screen.availableGeometry()
        self.chat_roster_panel.setGeometry(available)
        self.chat_roster_background.setGeometry(self.chat_roster_panel.rect())
        if hasattr(self, "tab_bg_pixmap") and not self.tab_bg_pixmap.isNull():
            self.chat_roster_background.setPixmap(
                self.tab_bg_pixmap.scaled(self.chat_roster_panel.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.chat_roster_background.clear()
        self.chat_roster_content.setGeometry(self.chat_roster_panel.rect())

    def _resolve_chat_avatar_pixmap(self, avatar_name: str) -> QPixmap:
        avatar = self.thumbnail_pixmaps.get(avatar_name, QPixmap()) if hasattr(self, "thumbnail_pixmaps") else QPixmap()
        if avatar.isNull():
            avatar = self.hog_thumb_pixmap if hasattr(self, "hog_thumb_pixmap") else QPixmap()
        slot_size = self._scaled_chat_metric("roster_slot_size", 48)
        if not hasattr(self, "roster_back_pixmap") or self.roster_back_pixmap.isNull():
            return avatar.scaledToHeight(slot_size, Qt.SmoothTransformation) if not avatar.isNull() else QPixmap()

        back_scale = max(0.1, self.chat_metrics["roster_back_scale"])
        avatar_scale = max(0.1, self.chat_metrics["roster_avatar_scale"])
        base_size = max(1, int(round(slot_size * back_scale)))
        avatar_size = max(1, int(round(slot_size * avatar_scale)))
        base = self.roster_back_pixmap.scaled(base_size, base_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        avatar_scaled = avatar.scaled(avatar_size, avatar_size, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not avatar.isNull() else QPixmap()

        offset_x = self._scaled_chat_metric("roster_avatar_offset_x")
        avatar_bottom_inset = self._scaled_chat_metric("roster_avatar_offset_y")
        back_offset_y = self._scaled_chat_metric("roster_back_offset_y")

        left_pad = max(0, -offset_x)
        right_pad = max(0, offset_x)
        canvas_width = max(base.width(), avatar_scaled.width() + left_pad + right_pad, slot_size)

        baseline = max(
            slot_size,
            avatar_scaled.height() + max(0, avatar_bottom_inset),
            base.height() + max(0, -back_offset_y),
        )
        canvas_height = baseline + max(0, back_offset_y)

        composed = QPixmap(canvas_width, canvas_height)
        composed.fill(Qt.transparent)
        painter = QPainter(composed)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        base_x = int((canvas_width - base.width()) / 2)
        base_y = baseline + back_offset_y - base.height()
        painter.drawPixmap(base_x, base_y, base)

        if not avatar_scaled.isNull():
            x = int((canvas_width - avatar_scaled.width()) / 2) + offset_x
            y = baseline - avatar_bottom_inset - avatar_scaled.height()
            painter.drawPixmap(x, y, avatar_scaled)

        painter.end()
        return composed

    def _update_chat_roster_window(self) -> None:
        if not hasattr(self, "chat_roster_rows_layout"):
            return
        users = list(self.chat_users.values())
        users.sort(key=lambda item: (0 if item.get("is_self") == "1" else 1, item.get("nickname", "")))

        while self.chat_roster_row_widgets:
            row_widget = self.chat_roster_row_widgets.pop()
            self.chat_roster_rows_layout.removeWidget(row_widget)
            row_widget.deleteLater()

        if not users:
            return

        per_row = 8
        slot_size = self._scaled_chat_metric("roster_slot_size", 48)
        row_gap = max(8, int(round(32 * self.resolution_scale)))
        slot_gap = max(10, int(round(26 * self.resolution_scale)))
        name_style = self._chat_roster_name_style()

        for start in range(0, len(users), per_row):
            row_users = users[start:start + per_row]
            row_widget = QWidget(self.chat_roster_rows_host)
            row_widget.setStyleSheet("QWidget { background: transparent; border: none; }")
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(slot_gap)
            row_layout.addStretch(1)

            for user in row_users:
                slot = QWidget(row_widget)
                slot.setStyleSheet("QWidget { background: transparent; border: none; }")
                slot_layout = QVBoxLayout(slot)
                slot_layout.setContentsMargins(0, 0, 0, 0)
                slot_layout.setSpacing(8)

                avatar = QLabel(slot)
                avatar.setAlignment(Qt.AlignCenter)
                avatar.setMinimumSize(slot_size, slot_size)
                pixmap = self._resolve_chat_avatar_pixmap(user.get("avatar_name", ""))
                avatar.setPixmap(pixmap if not pixmap.isNull() else QPixmap())

                name = QLabel(user.get("nickname", ""), slot)
                name.setAlignment(Qt.AlignCenter)
                name.setStyleSheet(name_style)

                slot_layout.addWidget(avatar, 0, Qt.AlignCenter)
                slot_layout.addWidget(name, 0, Qt.AlignCenter)
                row_layout.addWidget(slot, 0, Qt.AlignCenter)

            row_layout.addStretch(1)
            self.chat_roster_rows_layout.addWidget(row_widget, 0, Qt.AlignCenter)
            self.chat_roster_row_widgets.append(row_widget)

        self.chat_roster_rows_layout.setSpacing(row_gap)

    def _upsert_chat_user(self, client_id: str, nickname: str, avatar_name: str, is_self: bool = False) -> None:
        if not client_id:
            return
        self.chat_users[client_id] = {
            "nickname": nickname or "익명",
            "avatar_name": avatar_name or self.selected_thumbnail_name,
            "is_self": "1" if is_self else "0",
        }
        self._update_chat_roster_window()

    def _remove_chat_user(self, client_id: str) -> None:
        if client_id in self.chat_users:
            self.chat_users.pop(client_id, None)
            self._update_chat_roster_window()

    def _animate_chat_roster(self, visible: bool) -> None:
        if not hasattr(self, "chat_roster_panel"):
            return
        if not hasattr(self, "chat_roster_fade_animation") or not hasattr(self, "chat_roster_opacity"):
            if visible:
                self._position_chat_roster_window()
                self._update_chat_roster_window()
                self.chat_roster_panel.show()
                self.chat_roster_panel.raise_()
                self.chat_roster_visible = True
            else:
                self.chat_roster_panel.hide()
                self.chat_roster_visible = False
            return
        self.chat_roster_target_visible = visible
        self.chat_roster_fade_animation.stop()
        start_value = self.chat_roster_opacity.opacity()
        if visible:
            self._position_chat_roster_window()
            self._update_chat_roster_window()
            self.chat_roster_panel.show()
            self.chat_roster_panel.raise_()
            self.chat_roster_visible = True
            self.chat_roster_fade_animation.setDuration(max(0, int(self.chat_metrics["roster_fade_in_ms"])))
            self.chat_roster_fade_animation.setStartValue(start_value)
            self.chat_roster_fade_animation.setEndValue(1.0)
            self.chat_roster_fade_animation.start()
            self._raise_primary_overlays()
        else:
            if not self.chat_roster_panel.isVisible() and start_value <= 0.0:
                self.chat_roster_visible = False
                self.chat_roster_opacity.setOpacity(0.0)
                return
            self.chat_roster_fade_animation.setDuration(max(0, int(self.chat_metrics["roster_fade_out_ms"])))
            self.chat_roster_fade_animation.setStartValue(start_value)
            self.chat_roster_fade_animation.setEndValue(0.0)
            self.chat_roster_fade_animation.start()

    def _on_chat_roster_fade_finished(self) -> None:
        if not getattr(self, "chat_roster_target_visible", False):
            self.chat_roster_panel.hide()
            self.chat_roster_visible = False
            self.chat_roster_opacity.setOpacity(0.0)
        else:
            self.chat_roster_visible = True
            self.chat_roster_opacity.setOpacity(1.0)

    def _raise_primary_overlays(self) -> None:
        self.raise_()
        if hasattr(self, "chat_panel") and self.chat_panel.isVisible():
            self.chat_panel.raise_()

    def _show_chat_roster(self) -> None:
        if not self.is_logged_in or not self.chat_connected or not self.chat_users:
            return
        self._animate_chat_roster(True)
        self._raise_primary_overlays()

    def _hide_chat_roster(self) -> None:
        self._animate_chat_roster(False)

    def _position_chat_window(self) -> None:
        if not hasattr(self, "chat_panel"):
            return
        screen = QApplication.primaryScreen()
        width = int(round(self.chat_metrics["panel_width"] * self.resolution_scale))
        height = int(round(self.chat_metrics["panel_height"] * self.resolution_scale))
        if screen is None:
            self.chat_panel.setGeometry(
                self.chat_panel_pos_override.x() if self.chat_panel_pos_override is not None else int(round(self.chat_metrics["panel_left"] * self.resolution_scale)),
                self.chat_panel_pos_override.y() if self.chat_panel_pos_override is not None else 320,
                width,
                height,
            )
            return
        available = screen.availableGeometry()
        anchor_offset = int(round(self.chat_metrics["panel_anchor_y"] * self.resolution_scale))
        left = available.left() + int(round(self.chat_metrics["panel_left"] * self.resolution_scale))
        top = available.top() + int((available.height() - height) / 2) + anchor_offset
        if self.chat_panel_pos_override is not None:
            left = self.chat_panel_pos_override.x()
            top = self.chat_panel_pos_override.y()
        self.chat_panel.setGeometry(left, top, width, height)

    def _position_chat_notice_window(self) -> None:
        return

    def _set_chat_preview_mode(self, enabled: bool) -> None:
        self.chat_preview_mode = enabled
        if hasattr(self, "chat_preview_frame"):
            self.chat_preview_frame.hide()
        self.chat_history_frame.setVisible(True)
        self.chat_input_frame.setVisible(not enabled)
        self.chat_hint_label.setVisible(not enabled)
        if hasattr(self, "chat_preview_spacer"):
            self.chat_preview_spacer.setFixedHeight(self.chat_input_frame.sizeHint().height() + self.chat_hint_label.sizeHint().height() + self.chat_shell.layout().spacing())
            self.chat_preview_spacer.setVisible(enabled)
        if hasattr(self, "chat_history_frame_style"):
            self.chat_history_frame.setStyleSheet(self.chat_history_preview_style if enabled else self.chat_history_frame_style)
        self._refresh_chat_preview_items()

    def _refresh_chat_preview_items(self) -> None:
        if not hasattr(self, "chat_history"):
            return
        visible_preview_count = 0
        for row in range(self.chat_history.count()):
            item = self.chat_history.item(row)
            is_preview = bool(item.data(Qt.UserRole + 1))
            if self.chat_preview_mode:
                item.setHidden(not is_preview)
                if is_preview:
                    visible_preview_count += 1
            else:
                item.setHidden(False)
        if self.chat_preview_mode:
            self.chat_history.scrollToBottom()
            if visible_preview_count == 0 and hasattr(self, "chat_panel") and self.chat_panel.isVisible():
                self._hide_chat_panel()

    def _clear_chat_preview_items(self) -> None:
        self.chat_preview_mode = False
        for key, (_, timer) in list(self.chat_preview_timers.items()):
            timer.stop()
            self.chat_preview_timers.pop(key, None)
        if hasattr(self, "chat_history"):
            for row in range(self.chat_history.count()):
                item = self.chat_history.item(row)
                item.setData(Qt.UserRole + 1, False)
                item.setHidden(False)

    def _expire_chat_preview_item(self, item_id: int) -> None:
        entry = self.chat_preview_timers.pop(item_id, None)
        if entry is None:
            return
        item, timer = entry
        timer.stop()
        item.setData(Qt.UserRole + 1, False)
        if self.chat_preview_mode:
            item.setHidden(True)
            self._refresh_chat_preview_items()

    def _activate_chat_input(self) -> None:
        if not hasattr(self, "chat_enabled_checkbox") or not self.chat_enabled_checkbox.isChecked() or not self.is_logged_in:
            return
        self._show_chat_panel(focus_input=True)

    def _show_chat_panel(self, focus_input: bool = False) -> None:
        self._position_chat_window()
        self._clear_chat_preview_items()
        self._set_chat_preview_mode(False)
        self.chat_panel.show()
        self.chat_panel.raise_()
        self.chat_panel.activateWindow()
        if hasattr(self, "chat_hide_timer"):
            self.chat_hide_timer.stop()
        self.chat_history.scrollToBottom()
        if focus_input:
            self.chat_input.setFocus()

    def _hide_chat_panel_if_idle(self) -> None:
        if self.chat_preview_mode:
            self._hide_chat_panel()

    def _hide_chat_panel(self) -> None:
        if hasattr(self, "chat_panel"):
            self.chat_panel.hide()
        self.chat_preview_mode = False
        if hasattr(self, "chat_history"):
            for row in range(self.chat_history.count()):
                self.chat_history.item(row).setHidden(False)
        if hasattr(self, "chat_hide_timer"):
            self.chat_hide_timer.stop()

    def _restart_chat_hide_timer(self) -> None:
        return

    def _remove_chat_notice_card(self, card: QFrame) -> None:
        return

    def _hide_expired_chat_notices(self) -> None:
        return

    def _show_chat_notice(self, sender: str, text: str, color: str) -> None:
        if hasattr(self, "chat_panel") and self.chat_panel.isVisible() and not self.chat_preview_mode:
            return
        self._position_chat_window()
        last_item = self.chat_history.item(self.chat_history.count() - 1) if self.chat_history.count() else None
        if last_item is None:
            return
        self._set_chat_preview_mode(True)
        last_item.setData(Qt.UserRole + 1, True)
        last_item.setForeground(QColor(color))
        last_item.setHidden(False)
        lifetime_ms = (max(3, self.chat_hide_slider.value()) if hasattr(self, "chat_hide_slider") else 8) * 1000
        item_id = id(last_item)
        existing = self.chat_preview_timers.pop(item_id, None)
        if existing is not None:
            existing[1].stop()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda item_key=item_id: self._expire_chat_preview_item(item_key))
        timer.start(lifetime_ms)
        self.chat_preview_timers[item_id] = (last_item, timer)
        self.chat_panel.show()
        self.chat_panel.raise_()
        self.chat_panel.activateWindow()
        self.chat_history.scrollToBottom()
        self._refresh_chat_preview_items()

    def _chat_resize_hit_test(self, global_pos: QPoint) -> str:
        if not hasattr(self, "chat_panel"):
            return ""
        local = self.chat_panel.mapFromGlobal(global_pos)
        rect = self.chat_panel.rect()
        margin = max(8, int(round(10 * self.resolution_scale)))
        edges = ""
        if local.x() <= margin:
            edges += "left"
        elif local.x() >= rect.width() - margin:
            edges += "right"
        if local.y() <= margin:
            edges += "top"
        elif local.y() >= rect.height() - margin:
            edges += "bottom"
        return edges

    def _chat_resize_cursor(self, edges: str):
        if "left" in edges and "top" in edges or "right" in edges and "bottom" in edges:
            return Qt.SizeFDiagCursor
        if "right" in edges and "top" in edges or "left" in edges and "bottom" in edges:
            return Qt.SizeBDiagCursor
        if "left" in edges or "right" in edges:
            return Qt.SizeHorCursor
        if "top" in edges or "bottom" in edges:
            return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def _update_chat_resize_cursor(self, global_pos: QPoint) -> None:
        if not hasattr(self, "chat_panel"):
            return
        if self.chat_resize_edges:
            self.chat_panel.setCursor(self._chat_resize_cursor(self.chat_resize_edges))
            return
        edges = self._chat_resize_hit_test(global_pos)
        self.chat_panel.setCursor(self._chat_resize_cursor(edges))

    def _chat_mouse_press_event(self, event) -> None:
        if event.button() != Qt.LeftButton or not hasattr(self, "chat_panel"):
            return
        global_pos = event.globalPosition().toPoint()
        edges = self._chat_resize_hit_test(global_pos)
        if edges:
            self.chat_resize_edges = edges
            self.chat_resize_origin = global_pos
            self.chat_resize_start_geometry = self.chat_panel.geometry()
            self.chat_panel.setCursor(self._chat_resize_cursor(edges))
        else:
            self.chat_drag_origin = global_pos - self.chat_panel.frameGeometry().topLeft()
        event.accept()

    def _chat_mouse_move_event(self, event) -> None:
        if not hasattr(self, "chat_panel"):
            return
        global_pos = event.globalPosition().toPoint()
        if self.chat_resize_edges and self.chat_resize_origin is not None and self.chat_resize_start_geometry is not None and (event.buttons() & Qt.LeftButton):
            start = self.chat_resize_start_geometry
            delta = global_pos - self.chat_resize_origin
            min_width = max(260, int(round(260 * self.resolution_scale)))
            min_height = max(180, int(round(180 * self.resolution_scale)))
            left = start.left()
            top = start.top()
            width = start.width()
            height = start.height()
            if "right" in self.chat_resize_edges:
                width = max(min_width, start.width() + delta.x())
            if "bottom" in self.chat_resize_edges:
                height = max(min_height, start.height() + delta.y())
            if "left" in self.chat_resize_edges:
                new_left = start.left() + delta.x()
                max_left = start.right() - min_width + 1
                left = min(new_left, max_left)
                width = start.right() - left + 1
            if "top" in self.chat_resize_edges:
                new_top = start.top() + delta.y()
                max_top = start.bottom() - min_height + 1
                top = min(new_top, max_top)
                height = start.bottom() - top + 1
            self.chat_panel.setGeometry(left, top, width, height)
            self.chat_panel_pos_override = self.chat_panel.pos()
            self.chat_metrics["panel_width"] = max(1, int(round(width / self.resolution_scale)))
            self.chat_metrics["panel_height"] = max(1, int(round(height / self.resolution_scale)))
            self._rewrap_chat_history()
            event.accept()
            return
        if self.chat_drag_origin is not None and (event.buttons() & Qt.LeftButton):
            next_pos = global_pos - self.chat_drag_origin
            self.chat_panel.move(next_pos)
            self.chat_panel_pos_override = self.chat_panel.pos()
            event.accept()
            return
        self._update_chat_resize_cursor(global_pos)

    def _chat_mouse_release_event(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.chat_drag_origin = None
            self.chat_resize_origin = None
            self.chat_resize_start_geometry = None
            self.chat_resize_edges = ""
            if hasattr(self, "chat_panel"):
                self.chat_panel_pos_override = self.chat_panel.pos()
                self.chat_panel.setCursor(Qt.ArrowCursor)
            event.accept()

    def _sync_chat_identity_field(self) -> None:
        if hasattr(self, "chat_nickname_input") and hasattr(self, "username_input"):
            self.chat_nickname_input.setText(self.username_input.text().strip())

    def _chat_display_name(self) -> str:
        username = self.username_input.text().strip() if hasattr(self, "username_input") else ""
        return username or "익명"

    def _chat_config_from_ui(self) -> ChatConfig:
        room = self.chat_room_input.text().strip() or "attendance-room"
        group = self.chat_group_input.text().strip() or "239.255.42.99"
        try:
            port = int(self.chat_port_input.text().strip() or "45454")
        except ValueError:
            port = 45454
        return ChatConfig(
            nickname=self._chat_display_name(),
            room=room,
            multicast_group=group,
            port=port,
            system_messages=self.chat_system_checkbox.isChecked(),
            avatar_name=self.selected_thumbnail_name,
        )

    def _connect_chat_if_needed(self) -> None:
        if not hasattr(self, "chat_enabled_checkbox") or not self.chat_enabled_checkbox.isChecked() or not self.is_logged_in:
            return
        if self.chat_client is not None and self.chat_client.isRunning():
            return
        config = self._chat_config_from_ui()
        self.chat_client = LanChatClient(config, self)
        self.chat_client.message_received.connect(self._handle_chat_message)
        self.chat_client.connection_changed.connect(self._handle_chat_connection_changed)
        self.chat_client.error_occurred.connect(self._handle_chat_error)
        self.chat_client.start()
        self._upsert_chat_user(self.chat_client.client_id, self._chat_display_name(), self.selected_thumbnail_name, is_self=True)
        if not self.chat_presence_announced:
            text = f"{self._chat_display_name()} 님이 입장하셨습니다"
            self._append_chat_entry("시스템", text, system=True, color="#57d66b")
            self._show_chat_notice("시스템", text, "#57d66b")
            self.chat_presence_announced = True

    def _disconnect_chat(self) -> None:
        if self.chat_client is None:
            return
        leaving_client_id = self.chat_client.client_id
        if self.chat_presence_announced:
            text = f"{self._chat_display_name()} 님이 퇴장하셨습니다"
            self._append_chat_entry("시스템", text, system=True, color="#ff5a5a")
            self._show_chat_notice("시스템", text, "#ff5a5a")
        client = self.chat_client
        self.chat_client = None
        client.stop()
        self.chat_connected = False
        self.chat_presence_announced = False
        self._remove_chat_user(leaving_client_id)
        self._hide_chat_roster()
        self._hide_chat_panel()

    def _reconnect_chat(self) -> None:
        self._persist_chat_preferences()
        self._disconnect_chat()
        if self.is_logged_in and self.chat_enabled_checkbox.isChecked():
            self._connect_chat_if_needed()

    def _persist_chat_preferences(self) -> None:
        self.qt_settings.setValue("chat_enabled", self.chat_enabled_checkbox.isChecked())
        self.qt_settings.setValue("chat_system_messages", self.chat_system_checkbox.isChecked())
        self.qt_settings.setValue("chat_room", self.chat_room_input.text().strip())
        self.qt_settings.setValue("chat_group", self.chat_group_input.text().strip())
        self.qt_settings.setValue("chat_port", self.chat_port_input.text().strip())
        self.qt_settings.setValue("chat_hide_seconds", self.chat_hide_slider.value())
        self.qt_settings.setValue("chat_panel_opacity", self.chat_opacity_slider.value())
        self.qt_settings.sync()

    def _wrap_chat_text(self, text: str) -> str:
        available_width = max(180, self.chat_history.viewport().width() - 10) if hasattr(self, "chat_history") else 320
        font_size = max(12, int(round(self.chat_metrics['message_font_size'] * self.resolution_scale)))
        approx_char_width = max(6, int(font_size * 0.68))
        chars_per_line = max(12, available_width // approx_char_width)

        wrapped_lines: list[str] = []
        for raw_line in text.splitlines() or [text]:
            line = raw_line
            while len(line) > chars_per_line:
                split_at = line.rfind(' ', 0, chars_per_line)
                if split_at <= 0:
                    split_at = chars_per_line
                wrapped_lines.append(line[:split_at].rstrip())
                line = line[split_at:].lstrip()
            wrapped_lines.append(line)
        return "\n".join(wrapped_lines)

    def _rewrap_chat_history(self) -> None:
        if not hasattr(self, "chat_history"):
            return
        for row in range(self.chat_history.count()):
            item = self.chat_history.item(row)
            raw_line = item.data(Qt.UserRole + 2)
            if not raw_line:
                continue
            item.setText(self._wrap_chat_text(str(raw_line)))
            item.setSizeHint(item.sizeHint())
        self.chat_history.updateGeometry()

    def _append_chat_entry(self, sender: str, text: str, system: bool = False, timestamp: float | None = None, color: str | None = None) -> QListWidgetItem:
        when = datetime.fromtimestamp(timestamp) if timestamp else datetime.now()
        prefix = when.strftime("%H:%M")
        raw_line = f"[{prefix}] {text}" if system else f"[{prefix}] {sender}: {text}"
        line = self._wrap_chat_text(raw_line)
        item = QListWidgetItem(line)
        item.setData(Qt.UserRole + 1, False)
        item.setData(Qt.UserRole + 2, raw_line)
        item.setData(Qt.UserRole + 3, color or ("#00d9ff" if not system else "#00d9ff"))
        item.setForeground(QColor(color or ("#00d9ff" if not system else "#00d9ff")))
        item.setSizeHint(item.sizeHint())
        self.chat_history.addItem(item)
        while self.chat_history.count() > 60:
            removed = self.chat_history.takeItem(0)
            self.chat_preview_timers.pop(id(removed), None)
        self.chat_history.scrollToBottom()
        return item

    def _send_chat_message(self, text: str) -> None:
        if not text.strip():
            return
        self._connect_chat_if_needed()
        if self.chat_client is None:
            self._handle_chat_error("채팅 연결을 시작할 수 없습니다.")
            return
        self.chat_client.send_chat(text)
        self._append_chat_entry(self._chat_display_name(), text, system=False, color="#003cff")
        self._show_chat_panel(focus_input=True)

    def _handle_chat_message(self, message: dict) -> None:
        message_type = message.get("type")
        sender = str(message.get("sender", "알 수 없음"))
        sender_client_id = str(message.get("client_id", ""))
        avatar_name = str(message.get("avatar_name", ""))
        timestamp = float(message.get("timestamp", 0) or 0)
        if message_type == "system":
            event = message.get("event")
            if event in {"join", "presence"}:
                self._upsert_chat_user(sender_client_id, sender, avatar_name)
                if event == "presence":
                    return
                text = f"{sender} 님이 입장하셨습니다"
                color = "#57d66b"
            elif event == "leave":
                self._remove_chat_user(sender_client_id)
                text = f"{sender} 님이 퇴장하셨습니다"
                color = "#ff5a5a"
            else:
                return
            self._append_chat_entry("시스템", text, system=True, timestamp=timestamp, color=color)
            self._show_chat_notice("시스템", text, color)
            return
        self._upsert_chat_user(sender_client_id, sender, avatar_name)
        chat_text = str(message.get("text", ""))
        self._append_chat_entry(sender, chat_text, system=False, timestamp=timestamp, color="#8fefff")
        self._show_chat_notice(sender, chat_text, "#8fefff")

    def _handle_chat_status(self, status: str) -> None:
        return

    def _handle_chat_connection_changed(self, connected: bool) -> None:
        self.chat_connected = connected
        if not connected:
            self.chat_users.clear()
            self._hide_chat_roster()
            self._update_chat_roster_window()
        self.chat_reconnect_button.setEnabled(self.chat_enabled_checkbox.isChecked())

    def _handle_chat_error(self, message: str) -> None:
        return

    def _on_chat_enabled_toggled(self, checked: bool) -> None:
        self.chat_reconnect_button.setEnabled(checked)
        self.qt_settings.setValue("chat_enabled", checked)
        if checked and self.is_logged_in:
            self._connect_chat_if_needed()
        elif not checked:
            self._disconnect_chat()

    def _on_chat_system_messages_toggled(self, checked: bool) -> None:
        self.qt_settings.setValue("chat_system_messages", checked)
        if self.chat_client is not None and self.chat_client.isRunning():
            self._reconnect_chat()

    def _on_chat_settings_edited(self) -> None:
        self._persist_chat_preferences()
        if self.chat_client is not None and self.chat_client.isRunning() and self.chat_enabled_checkbox.isChecked():
            self._reconnect_chat()

    def _chat_scrollbar_style(self) -> str:
        scroll_handle_radius = max(4, int(round(self.chat_metrics["scrollbar_radius"] * self.resolution_scale)))
        return (
            "QScrollBar:vertical {"
            " background: transparent;"
            f" width: {max(8, int(round(self.chat_metrics['scrollbar_width'] * self.resolution_scale)))}px;"
            f" margin: {max(0, int(round(self.chat_metrics['scrollbar_margin_top'] * self.resolution_scale)))}px {max(0, int(round(self.chat_metrics['scrollbar_margin_right'] * self.resolution_scale)))}px {max(0, int(round(self.chat_metrics['scrollbar_margin_bottom'] * self.resolution_scale)))}px 0px;"
            " border: none;"
            "}"
            "QScrollBar::handle:vertical {"
            " background: rgba(245, 248, 255, 0.78);"
            f" border-radius: {scroll_handle_radius}px;"
            f" min-height: {max(24, int(round(self.chat_metrics['scrollbar_handle_min_height'] * self.resolution_scale)))}px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            " height: 0px;"
            " background: transparent;"
            " border: none;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            " background: transparent;"
            "}"
        )

    def _apply_chat_font_size(self) -> None:
        history_font_size = max(10, int(round(self.chat_metrics['message_font_size'] * self.resolution_scale)))
        input_font_size = max(10, int(round(self.chat_metrics['input_font_size'] * self.resolution_scale)))
        self.chat_history.setStyleSheet(
            f"QListWidget {{ background: transparent; color: rgba(242,247,255,0.95); border: none; outline: none; font-family: '{self.chat_font_family}'; font-size: {history_font_size}px; padding-right: 4px; }}"
            "QListWidget::item { padding: 4px 2px; border: none; }"
            + self._chat_scrollbar_style()
        )
        self.chat_input.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; color: #f3f8ff; border: none; padding: {self._scaled_chat_metric('input_text_padding_y')}px {self._scaled_chat_metric('input_text_padding_x')}px; font-family: '{self.chat_font_family}'; font-size: {input_font_size}px; }}"
            f"QPlainTextEdit[placeholderText] {{ color: rgba(211,224,240,0.46); }}"
            + self._chat_scrollbar_style()
        )

    def _on_chat_font_size_changed(self, value: int) -> None:
        value = max(10, min(32, value))
        self.chat_metrics['message_font_size'] = value
        self.chat_metrics['input_font_size'] = value
        self.chat_font_size_value_label.setText(f"{value}px")
        self.qt_settings.setValue("chat_font_size", value)
        self._apply_chat_font_size()

    def _on_chat_hide_seconds_changed(self, value: int) -> None:
        value = max(3, min(30, value))
        self.chat_hide_value_label.setText(f"{value}초")
        self.qt_settings.setValue("chat_hide_seconds", value)
        self._restart_chat_hide_timer()

    def _on_chat_opacity_changed(self, value: int) -> None:
        value = max(20, min(100, value))
        self.chat_panel.setWindowOpacity(value / 100)
        self.chat_opacity_value_label.setText(f"{value}%")
        self.qt_settings.setValue("chat_panel_opacity", value)

    def _create_settings_card(self, title: str, subtitle: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame(self.details_panel)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title_label = QLabel(title, card)
        title_label.setStyleSheet(
            f"color: #7aeaff; font-family: '{self.font_family}'; font-size: {self._scaled_metric('section_title_font_size')}px; font-weight: 400; background: transparent;"
        )
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle, card)
        subtitle_label.setStyleSheet(
            f"color: rgba(232,240,255,0.72); font-family: '{self.font_family}'; font-size: {self._scaled_metric('section_subtitle_font_size')}px; background: transparent;"
        )
        layout.addWidget(subtitle_label)

        self.settings_cards.append(card)
        return card, layout

    def _add_setting_row(self, parent_layout: QVBoxLayout, label_text: str, control, compact: bool = False, label_width: int | None = None) -> None:
        row = QFrame(self.details_panel)
        row.setObjectName("settingRow")
        row.setStyleSheet(self._row_panel_style())
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(16, 10 if compact else 12, 16, 10 if compact else 12)
        row_layout.setSpacing(16)

        label = QLabel(label_text, row)
        label.setStyleSheet(self._settings_label_style())
        if label_width is None:
            label.setMinimumWidth(self._scaled_metric("row_label_width_compact") if compact else self._scaled_metric("row_label_width"))
        else:
            label.setMinimumWidth(max(1, int(round(label_width * self.resolution_scale))))
        row_layout.addWidget(label, 0, Qt.AlignVCenter)

        if isinstance(control, QWidget):
            if control.minimumWidth() > 0 or control.maximumWidth() < 16777215:
                row_layout.addWidget(control, 0, Qt.AlignLeft | Qt.AlignVCenter)
                row_layout.addStretch(1)
            else:
                row_layout.addWidget(control, 1)
        else:
            row_layout.addLayout(control, 1)

        parent_layout.addWidget(row)

    def _settings_label_style(self) -> str:
        return (
            f"color: rgba(232,240,255,0.92); font-family: '{self.font_family}'; "
            f"font-size: {self._scaled_metric('row_label_font_size')}px; background: transparent;"
        )

    def _settings_value_style(self) -> str:
        return (
            f"color: #d9f8ff; font-family: '{self.font_family}'; "
            f"font-size: {self._scaled_metric('row_value_font_size')}px; min-width: 56px; background: transparent;"
        )

    def _row_panel_style(self) -> str:
        return "QFrame { background: rgba(7, 12, 18, 210); border: none; border-radius: 0px; }"

    def _settings_checkbox_style(self) -> str:
        return (
            f"QCheckBox {{ color: rgba(232,240,255,0.92); font-family: '{self.font_family}'; font-size: {self._scaled_metric('checkbox_font_size')}px; spacing: 10px; background: transparent; }}"
            "QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid rgba(255,255,255,0.35); background: rgba(255,255,255,0.06); }"
            "QCheckBox::indicator:checked { background: #38e4ff; border-color: #38e4ff; }"
        )

    def _slider_style(self) -> str:
        return (
            "QSlider::groove:horizontal { height: 6px; background: rgba(255,255,255,0.14); }"
            "QSlider::sub-page:horizontal { background: #39e6ff; }"
            "QSlider::handle:horizontal { width: 14px; margin: -5px 0; background: #f3fbff; border: 1px solid rgba(15,24,36,0.45); }"
        )

    def _accent_button_style(self) -> str:
        return (
            f"QPushButton {{ background: #36e0ff; color: #102030; border: none; padding: 8px 18px; font-family: '{self.font_family}'; font-size: {self._scaled_metric('button_font_size')}px; }}"
            "QPushButton:hover { background: #72ecff; }"
            "QPushButton:disabled { background: rgba(54,224,255,0.25); color: rgba(16,32,48,0.55); }"
        )

    def _action_button_style(self) -> str:
        return (
            f"QPushButton {{ background: rgba(255,255,255,0.08); color: rgba(235,243,255,0.94); border: 1px solid rgba(255,255,255,0.08); padding: 8px 18px; font-family: '{self.font_family}'; font-size: {self._scaled_metric('action_button_font_size')}px; }}"
            "QPushButton:hover { background: rgba(255,255,255,0.16); }"
            "QPushButton:disabled { background: rgba(255,255,255,0.04); color: rgba(255,255,255,0.3); }"
        )

    def _field_style(self, font_size_key: str = "field_font_size") -> str:
        font_size = int(round(self.settings_metrics.get(font_size_key, self.settings_metrics["field_font_size"]) * self.resolution_scale))
        return (
            f"QLineEdit {{ background: rgba(241,246,255,0.96); color: #1a2533; border: none; padding: 8px 12px; font-family: '{self.font_family}'; font-size: {font_size}px; }}"
            "QLineEdit::placeholder { color: rgba(26,37,51,0.45); }"
        )

    def _switch_settings_tab(self, index: int) -> None:
        self.settings_stack.setCurrentIndex(index)
        for idx, button in enumerate(self.settings_tab_buttons):
            active = idx == index
            button.setChecked(active)
            button.setStyleSheet(
                f"QPushButton {{ background: {'#36e0ff' if active else 'rgba(25,37,54,0.88)'}; color: {'#112236' if active else 'rgba(236,244,255,0.82)'}; border: none; padding: 8px 16px; font-family: '{self.font_family}'; font-size: {self._scaled_metric('tab_font_size')}px; }}"
                f"QPushButton:hover {{ background: {'#5ce8ff' if active else 'rgba(36,52,74,0.96)'}; }}"
            )
        self._update_settings_hit_region()

    def _scaled_decoration_pixmap(self, pixmap: QPixmap, scale: float) -> QPixmap:
        if pixmap.isNull():
            return QPixmap()
        width = max(1, int(pixmap.width() * scale * self.resolution_scale))
        height = max(1, int(pixmap.height() * scale * self.resolution_scale))
        return pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _layout_hud_decorations(self) -> None:
        overlay_size = self.details_panel.size()

        left_thumb = self._scaled_decoration_pixmap(self.hog_thumb_pixmap, self.hud_metrics["left_thumb_scale"])
        left_hp = self._scaled_decoration_pixmap(self.hp_icon_pixmap, self.hud_metrics["left_hp_scale"])
        center_q = self._scaled_decoration_pixmap(self.q_skill_pixmap, self.hud_metrics["center_q_scale"])
        right_skill = self._scaled_decoration_pixmap(self.hog_skill_pixmap, self.hud_metrics["right_skill_scale"])
        right_gun = self._scaled_decoration_pixmap(self.hog_gun_pixmap, self.hud_metrics["right_gun_scale"])

        self.left_hud_thumb.setPixmap(left_thumb)
        self.left_hud_hp.setPixmap(left_hp)
        self.center_hud_q.setPixmap(center_q)
        self.right_hud_skill.setPixmap(right_skill)
        self.right_hud_gun.setPixmap(right_gun)

        if not left_thumb.isNull():
            self.left_hud_thumb.resize(left_thumb.size())
            self.left_hud_thumb.move(self._scaled_hud_metric("left_thumb_padding_x"), overlay_size.height() - self._scaled_hud_metric("left_thumb_padding_y") - left_thumb.height())
        if not left_hp.isNull():
            self.left_hud_hp.resize(left_hp.size())
            hp_x = self._scaled_hud_metric("left_thumb_padding_x") + self.left_hud_thumb.width() + self._scaled_hud_metric("left_hp_gap") + self._scaled_hud_metric("left_hp_padding_x")
            hp_y = overlay_size.height() - self._scaled_hud_metric("left_hp_padding_y") - left_hp.height()
            self.left_hud_hp.move(hp_x, hp_y)

        if not center_q.isNull():
            self.center_hud_q.resize(center_q.size())
            center_x = int((overlay_size.width() - center_q.width()) / 2 + self._scaled_hud_metric("center_q_offset_x"))
            center_y = overlay_size.height() - self._scaled_hud_metric("center_q_padding_y") - center_q.height()
            self.center_hud_q.move(center_x, center_y)

        if not right_gun.isNull():
            self.right_hud_gun.resize(right_gun.size())
            gun_x = overlay_size.width() - self._scaled_hud_metric("right_gun_padding_x") - right_gun.width()
            gun_y = overlay_size.height() - self._scaled_hud_metric("right_gun_padding_y") - right_gun.height()
            self.right_hud_gun.move(gun_x, gun_y)
        if not right_skill.isNull():
            self.right_hud_skill.resize(right_skill.size())
            skill_x = self.right_hud_gun.x() - self._scaled_hud_metric("right_gun_gap") - right_skill.width() if not right_gun.isNull() else overlay_size.width() - self._scaled_hud_metric("right_skill_padding_x") - right_skill.width()
            skill_x -= self._scaled_hud_metric("right_skill_padding_x") if not right_gun.isNull() else 0
            skill_y = overlay_size.height() - self._scaled_hud_metric("right_skill_padding_y") - right_skill.height()
            self.right_hud_skill.move(skill_x, skill_y)

    def _resize_settings_window(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            self.details_panel.setFixedSize(int(1280 * self.resolution_scale), int(720 * self.resolution_scale))
            self.settings_stack.setFixedWidth(int(760 * self.resolution_scale))
            self._layout_hud_decorations()
            self._position_chat_window()
            self._position_chat_notice_window()
            return
        available = screen.availableGeometry()
        self.details_panel.setGeometry(available)
        card_width = max(int(620 * self.resolution_scale), min(int(860 * self.resolution_scale), int(available.width() * 0.46)))
        self.settings_stack.setFixedWidth(card_width)
        for card in self.settings_cards:
            card.setFixedWidth(card_width)
        self._layout_hud_decorations()
        self._position_chat_window()
        self._position_chat_notice_window()
        self._update_settings_hit_region()

    def _position_settings_window(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.details_panel.setGeometry(available)
        self._resize_settings_window()
        self._update_settings_hit_region()

    def _update_settings_hit_region(self) -> None:
        if not self.details_panel.isVisible():
            self.details_panel.clearMask()
            return
        region = QRegion()
        for widget in [self.settings_header, self.settings_stack.currentWidget(), self.left_hud_thumb, self.left_hud_hp, self.center_hud_q, self.right_hud_skill, self.right_hud_gun]:
            if widget is None or not widget.isVisible():
                continue
            top_left = widget.mapTo(self.details_panel, QPoint(0, 0))
            region = region.united(QRegion(widget.rect().translated(top_left)))
            for child in widget.findChildren(QWidget):
                if not child.isVisible() or child.parentWidget() is None:
                    continue
                child_top_left = child.mapTo(self.details_panel, QPoint(0, 0))
                region = region.united(QRegion(child.rect().translated(child_top_left)))
        self.details_panel.setMask(region)

    def _apply_details_background(self, opacity_percent: int) -> None:
        opacity_percent = max(10, min(90, opacity_percent))
        row_alpha = int(160 + (opacity_percent / 90) * 70)
        for card in self.settings_cards:
            card.setStyleSheet("QFrame { background: transparent; border: none; }")
        for row in self.details_panel.findChildren(QFrame, "settingRow"):
            row.setStyleSheet(
                f"QFrame#settingRow {{ background: rgba(7, 12, 18, {row_alpha}); border: none; border-radius: 0px; }}"
            )
        self.details_panel.update()

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

        saved_card_opacity = self.qt_settings.value("card_window_opacity", 90, type=int)
        saved_card_opacity = max(10, min(90, int(saved_card_opacity)))
        self.card_opacity_slider.setValue(saved_card_opacity)
        self.setWindowOpacity(saved_card_opacity / 100)
        self.card_opacity_value_label.setText(f"{saved_card_opacity}%")

        saved_ui_opacity = self.qt_settings.value("ui_window_opacity", 90, type=int)
        saved_ui_opacity = max(10, min(90, int(saved_ui_opacity)))
        self.ui_opacity_slider.setValue(saved_ui_opacity)
        self.details_panel.setWindowOpacity(saved_ui_opacity / 100)
        self._apply_details_background(saved_ui_opacity)
        self.ui_opacity_value_label.setText(f"{saved_ui_opacity}%")

        saved_interval = self.qt_settings.value("refresh_interval_seconds", 10, type=int)
        saved_interval = max(10, min(300, int(saved_interval)))
        self.refresh_interval_slider.setValue(saved_interval)
        self.refresh_timer.setInterval(saved_interval * 1000)
        self.refresh_interval_value_label.setText(self._format_refresh_interval(saved_interval))

        self.chat_enabled_checkbox.setChecked(self.qt_settings.value("chat_enabled", True, type=bool))
        self.chat_system_checkbox.setChecked(self.qt_settings.value("chat_system_messages", True, type=bool))
        self._sync_chat_identity_field()
        self.chat_room_input.setText(self.qt_settings.value("chat_room", "attendance-room", type=str) or "attendance-room")
        self.chat_group_input.setText(self.qt_settings.value("chat_group", "239.255.42.99", type=str) or "239.255.42.99")
        self.chat_port_input.setText(self.qt_settings.value("chat_port", "45454", type=str) or "45454")
        saved_chat_font = max(10, min(32, int(self.qt_settings.value("chat_font_size", self.chat_metrics['message_font_size'], type=int))))
        self.chat_font_size_slider.setValue(saved_chat_font)
        self.chat_font_size_value_label.setText(f"{saved_chat_font}px")
        self.chat_metrics['message_font_size'] = saved_chat_font
        self.chat_metrics['input_font_size'] = saved_chat_font
        self._apply_chat_font_size()
        saved_chat_hide = max(3, min(30, int(self.qt_settings.value("chat_hide_seconds", 8, type=int))))
        self.chat_hide_slider.setValue(saved_chat_hide)
        self.chat_hide_value_label.setText(f"{saved_chat_hide}초")
        saved_chat_opacity = max(20, min(100, int(self.qt_settings.value("chat_panel_opacity", 92, type=int))))
        self.chat_opacity_slider.setValue(saved_chat_opacity)
        self.chat_panel.setWindowOpacity(saved_chat_opacity / 100)
        self.chat_opacity_value_label.setText(f"{saved_chat_opacity}%")
        self.chat_reconnect_button.setEnabled(self.chat_enabled_checkbox.isChecked())

    def _save_preferences(self) -> None:
        self.qt_settings.setValue("username", self.username_input.text().strip())
        self._sync_chat_identity_field()
        self.qt_settings.setValue("password", self.password_input.text())
        self.qt_settings.setValue("headless", self.headless_checkbox.isChecked())
        self.qt_settings.setValue("always_on_top", self.always_on_top_checkbox.isChecked())
        self.qt_settings.setValue("card_window_opacity", self.card_opacity_slider.value())
        self.qt_settings.setValue("ui_window_opacity", self.ui_opacity_slider.value())
        self.qt_settings.setValue("refresh_interval_seconds", self.refresh_interval_slider.value())
        self._persist_chat_preferences()
        self.qt_settings.sync()

    def _on_headless_toggled(self, checked: bool) -> None:
        self.settings.headless = checked
        self.qt_settings.setValue("headless", checked)
        self.qt_settings.sync()

    def _on_always_on_top_toggled(self, checked: bool) -> None:
        self._apply_window_flags(checked)
        self.qt_settings.setValue("always_on_top", checked)
        self.qt_settings.sync()

    def _on_card_opacity_changed(self, value: int) -> None:
        value = max(10, min(90, value))
        self.setWindowOpacity(value / 100)
        self.card_opacity_value_label.setText(f"{value}%")
        self.qt_settings.setValue("card_window_opacity", value)

    def _on_ui_opacity_changed(self, value: int) -> None:
        value = max(10, min(90, value))
        self.details_panel.setWindowOpacity(value / 100)
        self._apply_details_background(value)
        self.ui_opacity_value_label.setText(f"{value}%")
        self.qt_settings.setValue("ui_window_opacity", value)

    def _on_refresh_interval_changed(self, value: int) -> None:
        value = max(10, min(300, value))
        self.refresh_timer.setInterval(value * 1000)
        self.refresh_interval_value_label.setText(self._format_refresh_interval(value))
        self.qt_settings.setValue("refresh_interval_seconds", value)

    def close_and_exit(self) -> None:
        self.refresh_timer.stop()
        self._disconnect_chat()
        self.shutdown_requested.emit()
        self.session_thread.quit()
        self.session_thread.wait(2000)
        if self.details_panel is not None:
            self.details_panel.close()
        if hasattr(self, "chat_panel") and self.chat_panel is not None:
            self.chat_panel.close()
        if hasattr(self, "chat_roster_panel") and self.chat_roster_panel is not None:
            self.chat_roster_panel.close()
        if hasattr(self, "chat_notice_panel") and self.chat_notice_panel is not None:
            self.chat_notice_panel.close()
        self.close()
        QApplication.quit()

    def closeEvent(self, event) -> None:
        self.refresh_timer.stop()
        self._disconnect_chat()
        self.shutdown_requested.emit()
        self.session_thread.quit()
        self.session_thread.wait(2000)
        if self.details_panel is not None:
            self.details_panel.close()
        if hasattr(self, "chat_panel") and self.chat_panel is not None:
            self.chat_panel.close()
        if hasattr(self, "chat_roster_panel") and self.chat_roster_panel is not None:
            self.chat_roster_panel.close()
        if hasattr(self, "chat_notice_panel") and self.chat_notice_panel is not None:
            self.chat_notice_panel.close()
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
        if hasattr(self, "snapshot") and self.snapshot is not None:
            self._update_today_action_buttons(self.snapshot)
        else:
            self.work_in_button.setEnabled(self.is_logged_in and not busy)
            self.work_out_button.setEnabled(self.is_logged_in and not busy)
        if not self.is_logged_in:
            self.login_button.setEnabled(not busy)
            self.headless_checkbox.setEnabled(not busy)
    def _set_logged_in_ui(self, logged_in: bool) -> None:
        self.is_logged_in = logged_in
        self.username_input.setEnabled(not logged_in)
        self.password_input.setEnabled(not logged_in)
        self.login_button.setEnabled(not logged_in and not self.is_busy)
        self.headless_checkbox.setEnabled(not logged_in and not self.is_busy)
        self.refresh_button.setEnabled(logged_in and not self.is_busy)
        self.work_in_button.setEnabled(logged_in and not self.is_busy)
        self.work_out_button.setEnabled(logged_in and not self.is_busy)
        if not logged_in:
            self.work_in_time_label.setText("")
            self.work_out_time_label.setText("")

    def _handle_login_success(self, snapshot: AttendanceSnapshot) -> None:
        self._set_logged_in_ui(True)
        self.snapshot = snapshot
        self._update_summary_ui(snapshot)
        self.status_label.setText("접속 완료. 숨깨진 브라우저 세션이 초과근무 페이지에서 실행 중입니다.")
        self.refresh_timer.start()
        self._connect_chat_if_needed()
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

    def _update_today_action_buttons(self, snapshot: AttendanceSnapshot) -> None:
        today_date = date.today().strftime("%Y%m%d")
        today_row = snapshot.today if snapshot.today and snapshot.today.date == today_date else None
        if today_row is None:
            for row in snapshot.weekly_rows:
                if row.date == today_date:
                    today_row = row
                    break

        raw_come = (today_row.come_time or "") if today_row is not None else ""
        raw_leave = (today_row.leave_time or "") if today_row is not None else ""
        self.work_in_time_label.setText(self._format_clock(raw_come) if raw_come else "")
        self.work_out_time_label.setText(self._format_clock(raw_leave) if raw_leave else "")
        self.work_in_button.setEnabled(self.is_logged_in and not self.is_busy and not raw_come)
        self.work_out_button.setEnabled(self.is_logged_in and not self.is_busy)

    def _update_summary_ui(self, snapshot: AttendanceSnapshot) -> None:
        balance_minutes = snapshot.summary.balance_minutes
        self._update_score_card(balance_minutes)
        self.status_label.setText(
            f"누적 {snapshot.summary.week_minutes // 60}h {(snapshot.summary.week_minutes % 60):02d}m / "
            f"기준 {snapshot.summary.expected_minutes // 60}h {(snapshot.summary.expected_minutes % 60):02d}m"
        )
        self._update_day_rows(snapshot)
        self._update_today_action_buttons(snapshot)

    def _update_score_card(self, balance_minutes: int) -> None:
        self.current_balance_minutes = balance_minutes
        self.score_text_left = f"{self._format_duration(abs(min(balance_minutes, 0)))}"
        self.score_text_right = f"{self._format_duration(max(balance_minutes, 0))}"
        base_pixmap = self.red_bg if balance_minutes >= 0 else self.blue_bg
        if self.card_loading:
            self.card_pixmap = self.red_bg_dim if balance_minutes >= 0 else self.blue_bg_dim
        else:
            self.card_pixmap = base_pixmap

        if balance_minutes >= 0:
            self.score_label_left.setStyleSheet("color: rgb(0,200,220); background: transparent;")
            self.score_label_right.setStyleSheet("color: white; background: transparent;")
        else:
            self.score_label_left.setStyleSheet("color: white; background: transparent;")
            self.score_label_right.setStyleSheet("color: rgb(220,2,5); background: transparent;")

        self.score_label_left.setText(self.score_text_left)
        self.score_label_right.setText(self.score_text_right)
        self._apply_card_geometry()

    def _update_day_rows(self, snapshot: AttendanceSnapshot) -> None:
        rows_by_date = {row.date: row for row in snapshot.weekly_rows}
        target_dates = week_date_strings(date.today())
        day_data: list[dict[str, object]] = []
        for order_index, (day_name, day_key) in enumerate(zip(DAY_NAMES, target_dates)):
            row = rows_by_date.get(day_key)
            if row is None:
                day_data.append(
                    {
                        'day_name': day_name,
                        'balance_minutes': 0,
                        'come_time': '--:--',
                        'leave_time': '--:--',
                        'order_index': order_index,
                    }
                )
                continue
            come_time, leave_time = normalize_times(row, self.settings.default_start, self.settings.default_end)
            worked = worked_minutes(come_time, leave_time)
            expected = target_minutes_for_label(row.label, self.settings.weekday_target_minutes, self.settings.halfday_target_minutes)
            balance_minutes = worked - expected
            day_data.append(
                {
                    'day_name': day_name,
                    'balance_minutes': balance_minutes,
                    'come_time': self._format_clock(come_time),
                    'leave_time': self._format_clock(leave_time),
                    'order_index': order_index,
                }
            )

        self.weekly_table.set_rows(day_data)

    def _toggle_details(self, checked: bool) -> None:
        self.details_panel.setVisible(checked)
        if checked:
            self._position_settings_window()
            self.details_panel.raise_()
            self.details_panel.activateWindow()
        self._refresh_details_layout()

    def _refresh_details_layout(self) -> None:
        if self.details_panel.isVisible():
            self.details_panel.adjustSize()
            self._position_settings_window()
            self.details_panel.update()
        self.adjustSize()
        self.update()

    def _apply_window_flags(self, always_on_top: bool) -> None:
        geometry = self.geometry()
        was_visible = self.isVisible()
        details_visible = self.details_panel.isVisible()
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setWindowFlag(Qt.Tool, True)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, always_on_top)
        self.details_panel.setWindowFlag(Qt.FramelessWindowHint, True)
        self.details_panel.setWindowFlag(Qt.Tool, True)
        self.details_panel.setWindowFlag(Qt.WindowStaysOnTopHint, always_on_top)
        if hasattr(self, "chat_panel"):
            self.chat_panel.setWindowFlag(Qt.FramelessWindowHint, True)
            self.chat_panel.setWindowFlag(Qt.Tool, True)
            self.chat_panel.setWindowFlag(Qt.WindowStaysOnTopHint, always_on_top)
        if hasattr(self, "chat_roster_panel"):
            self.chat_roster_panel.setWindowFlag(Qt.FramelessWindowHint, True)
            self.chat_roster_panel.setWindowFlag(Qt.Tool, True)
            self.chat_roster_panel.setWindowFlag(Qt.WindowStaysOnTopHint, always_on_top)
        if hasattr(self, "chat_notice_panel") and self.chat_notice_panel is not None:
            self.chat_notice_panel.setWindowFlag(Qt.FramelessWindowHint, True)
            self.chat_notice_panel.setWindowFlag(Qt.Tool, True)
            self.chat_notice_panel.setWindowFlag(Qt.WindowStaysOnTopHint, always_on_top)
        if was_visible:
            self.show()
            self.setGeometry(geometry)
        if details_visible:
            self.details_panel.show()
            self._position_settings_window()
        if hasattr(self, "chat_panel") and self.chat_panel.isVisible():
            self.chat_panel.show()
            self._position_chat_window()
        if hasattr(self, "chat_roster_panel") and self.chat_roster_panel.isVisible():
            self.chat_roster_panel.show()
            self._position_chat_roster_window()
        if hasattr(self, "chat_notice_panel") and self.chat_notice_panel is not None and self.chat_notice_panel.isVisible():
            self.chat_notice_panel.show()
            self._position_chat_notice_window()
            self._position_chat_notice_window()

    def _apply_card_geometry(self) -> None:
        active_pixmap = self.card_pixmap if not self.card_pixmap.isNull() else self.blue_bg
        image_scale = self.card_metrics["image_scale"]
        effective_scale = self.scale * self.resolution_scale
        scaled_width = int(active_pixmap.width() * image_scale * effective_scale) if not active_pixmap.isNull() else int(260 * self.resolution_scale)
        scaled_height = int(active_pixmap.height() * image_scale * effective_scale) if not active_pixmap.isNull() else int(90 * self.resolution_scale)
        self.card.setFixedSize(scaled_width, scaled_height)
        self.setFixedSize(scaled_width, scaled_height)

        if not active_pixmap.isNull():
            scaled = active_pixmap.scaled(scaled_width, scaled_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.bg_label.setPixmap(scaled)
            self.bg_label.setGeometry(0, 0, scaled_width, scaled_height)

        effective_scale = self.scale * self.resolution_scale
        score_font = self._display_font(max(12, int(25 * effective_scale)), italic=True)
        self.score_label_left.setFont(score_font)
        self.score_label_right.setFont(score_font)
        self.score_label_left.setGeometry(
            int(self.card_metrics["text_left_x"] * effective_scale),
            int(self.card_metrics["text_y"] * effective_scale),
            int(self.card_metrics["text_left_width"] * effective_scale),
            int(self.card_metrics["text_height"] * effective_scale),
        )
        self.score_label_right.setGeometry(
            scaled_width - int(self.card_metrics["text_right_x_offset"] * effective_scale),
            int(self.card_metrics["text_y"] * effective_scale),
            int(self.card_metrics["text_right_width"] * effective_scale),
            int(self.card_metrics["text_height"] * effective_scale),
        )
        self.update()

    def _format_duration(self, minutes: int) -> str:
        hours, remain = divmod(abs(minutes), 60)
        return f"{hours}:{remain:02d}"

    def _format_clock(self, value: str) -> str:
        if len(value) < 4:
            return "--:--"
        return f"{value[:2]}:{value[2:4]}"

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._resize_settings_window()
        if self.details_panel.isVisible():
            self._position_settings_window()
        self._position_chat_window()
        self._position_chat_roster_window()

    def eventFilter(self, obj, event) -> bool:
        active_window = QApplication.activeWindow()
        tracked_windows = {self, getattr(self, "details_panel", None), getattr(self, "chat_panel", None), getattr(self, "chat_roster_panel", None)}
        if active_window not in tracked_windows:
            return super().eventFilter(obj, event)
        if event.type() == QEvent.ShortcutOverride and event.key() == Qt.Key_Tab:
            event.accept()
            return True
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Tab and not event.isAutoRepeat():
            event.accept()
            if self.chat_roster_visible:
                self._hide_chat_roster()
            else:
                self._show_chat_roster()
            return True
        if event.type() == QEvent.KeyRelease and event.key() == Qt.Key_Tab and not event.isAutoRepeat():
            event.accept()
            return True
        return super().eventFilter(obj, event)

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
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(0, 0, 0, 100), 3))
        painter.drawLine(self.width() - 10, self.height() - 1, self.width() - 1, self.height() - 1)
        painter.drawLine(self.width() - 1, self.height() - 10, self.width() - 1, self.height() - 1)

    def _is_on_handle(self, pos: QPoint) -> bool:
        return pos.x() >= self.width() - 14 and pos.y() >= self.height() - 14




