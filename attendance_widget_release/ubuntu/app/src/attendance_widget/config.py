from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app_settings import (
    AFTER_ATTENDANCE_CLICK_DELAY_SECONDS,
    AFTER_CONFIRM_CLICK_DELAY_SECONDS,
    AFTER_LOGIN_CLICK_DELAY_SECONDS,
    AFTER_NEXT_CLICK_DELAY_SECONDS,
    AFTER_PASSWORD_DELAY_SECONDS,
    AFTER_USERNAME_DELAY_SECONDS,
    API_CAPTURE_DELAY_SECONDS,
    ATTENDANCE_PAGE_DELAY_SECONDS,
    CONFIRM_BUTTON_XPATH,
    DEFAULT_END,
    DEFAULT_START,
    HALFDAY_TARGET_MINUTES,
    HEADLESS,
    HOME_URL,
    LOGIN_PAGE_DELAY_SECONDS,
    LOGIN_URL,
    NEXT_BUTTON_XPATH,
    PASSWORD_FIELD_ID,
    SUBMIT_BUTTON_XPATH,
    TODAY_DATA_URL,
    USERNAME_FIELD_ID,
    WEEKDAY_TARGET_MINUTES,
    WEEKLY_DATA_URL,
    WEEKLY_PAGE_URL,
    WORK_IN_XPATH,
    WORK_OUT_XPATH,
)


load_dotenv()


@dataclass(slots=True)
class Settings:
    login_url: str
    home_url: str
    weekly_page_url: str
    weekly_data_url: str
    today_data_url: str
    username: str
    password: str
    username_field_id: str
    password_field_id: str
    next_button_xpath: str
    submit_button_xpath: str
    work_in_xpath: str
    work_out_xpath: str
    confirm_button_xpath: str
    default_start: str
    default_end: str
    weekday_target_minutes: int
    halfday_target_minutes: int
    headless: bool
    login_page_delay_seconds: float
    after_username_delay_seconds: float
    after_next_click_delay_seconds: float
    after_password_delay_seconds: float
    after_login_click_delay_seconds: float
    attendance_page_delay_seconds: float
    after_attendance_click_delay_seconds: float
    after_confirm_click_delay_seconds: float
    api_capture_delay_seconds: float


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def load_settings() -> Settings:
    return Settings(
        login_url=os.getenv("ATTENDANCE_LOGIN_URL", LOGIN_URL),
        home_url=os.getenv("ATTENDANCE_HOME_URL", HOME_URL),
        weekly_page_url=os.getenv("ATTENDANCE_WEEKLY_PAGE_URL", WEEKLY_PAGE_URL),
        weekly_data_url=os.getenv("ATTENDANCE_WEEKLY_DATA_URL", WEEKLY_DATA_URL),
        today_data_url=os.getenv("ATTENDANCE_TODAY_DATA_URL", TODAY_DATA_URL),
        username=os.getenv("ATTENDANCE_USERNAME", ""),
        password=os.getenv("ATTENDANCE_PASSWORD", ""),
        username_field_id=os.getenv("ATTENDANCE_USERNAME_FIELD_ID", USERNAME_FIELD_ID),
        password_field_id=os.getenv("ATTENDANCE_PASSWORD_FIELD_ID", PASSWORD_FIELD_ID),
        next_button_xpath=os.getenv("ATTENDANCE_NEXT_BUTTON_XPATH", NEXT_BUTTON_XPATH),
        submit_button_xpath=os.getenv("ATTENDANCE_SUBMIT_BUTTON_XPATH", SUBMIT_BUTTON_XPATH),
        work_in_xpath=os.getenv("ATTENDANCE_WORK_IN_XPATH", WORK_IN_XPATH),
        work_out_xpath=os.getenv("ATTENDANCE_WORK_OUT_XPATH", WORK_OUT_XPATH),
        confirm_button_xpath=os.getenv("ATTENDANCE_CONFIRM_BUTTON_XPATH", CONFIRM_BUTTON_XPATH),
        default_start=os.getenv("ATTENDANCE_DEFAULT_START", DEFAULT_START),
        default_end=os.getenv("ATTENDANCE_DEFAULT_END", DEFAULT_END),
        weekday_target_minutes=int(os.getenv("ATTENDANCE_WEEKDAY_TARGET_MINUTES", str(WEEKDAY_TARGET_MINUTES))),
        halfday_target_minutes=int(os.getenv("ATTENDANCE_HALFDAY_TARGET_MINUTES", str(HALFDAY_TARGET_MINUTES))),
        headless=_read_bool("ATTENDANCE_HEADLESS", HEADLESS),
        login_page_delay_seconds=_read_float("ATTENDANCE_LOGIN_PAGE_DELAY_SECONDS", LOGIN_PAGE_DELAY_SECONDS),
        after_username_delay_seconds=_read_float("ATTENDANCE_AFTER_USERNAME_DELAY_SECONDS", AFTER_USERNAME_DELAY_SECONDS),
        after_next_click_delay_seconds=_read_float("ATTENDANCE_AFTER_NEXT_CLICK_DELAY_SECONDS", AFTER_NEXT_CLICK_DELAY_SECONDS),
        after_password_delay_seconds=_read_float("ATTENDANCE_AFTER_PASSWORD_DELAY_SECONDS", AFTER_PASSWORD_DELAY_SECONDS),
        after_login_click_delay_seconds=_read_float("ATTENDANCE_AFTER_LOGIN_CLICK_DELAY_SECONDS", AFTER_LOGIN_CLICK_DELAY_SECONDS),
        attendance_page_delay_seconds=_read_float("ATTENDANCE_PAGE_DELAY_SECONDS", ATTENDANCE_PAGE_DELAY_SECONDS),
        after_attendance_click_delay_seconds=_read_float("ATTENDANCE_AFTER_ATTENDANCE_CLICK_DELAY_SECONDS", AFTER_ATTENDANCE_CLICK_DELAY_SECONDS),
        after_confirm_click_delay_seconds=_read_float("ATTENDANCE_AFTER_CONFIRM_CLICK_DELAY_SECONDS", AFTER_CONFIRM_CLICK_DELAY_SECONDS),
        api_capture_delay_seconds=_read_float("ATTENDANCE_API_CAPTURE_DELAY_SECONDS", API_CAPTURE_DELAY_SECONDS),
    )
