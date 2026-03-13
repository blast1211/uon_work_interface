from __future__ import annotations

import json
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, ElementNotInteractableException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from attendance_widget.calculations import build_weekly_summary
from attendance_widget.config import Settings
from attendance_widget.models import DailyAttendance, WeeklySummary


class AttendanceError(RuntimeError):
    """Raised when the attendance site interaction fails."""


@dataclass(slots=True)
class AttendanceSnapshot:
    today: DailyAttendance | None
    weekly_rows: list[DailyAttendance]
    summary: WeeklySummary


class AttendanceAutomation(AbstractContextManager["AttendanceAutomation"]):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.driver = self._create_driver()

    def _create_driver(self) -> webdriver.Chrome:
        options = webdriver.ChromeOptions()
        if self.settings.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1400,1000")
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})
        return webdriver.Chrome(options=options)

    def __exit__(self, exc_type, exc, tb) -> None:
        self.driver.quit()

    def close(self) -> None:
        self.driver.quit()

    def login(self, username: str, password: str) -> None:
        if not username or not password:
            raise AttendanceError("Login ID and password are required.")

        self.driver.get(self.settings.login_url)
        wait = WebDriverWait(self.driver, 20)

        username_field = wait.until(EC.element_to_be_clickable((By.ID, self.settings.username_field_id)))
        username_field.clear()
        username_field.send_keys(username)

        if self.settings.next_button_xpath:
            self._click_xpath(self.settings.next_button_xpath)

        password_field = wait.until(EC.element_to_be_clickable((By.ID, self.settings.password_field_id)))
        password_field.clear()
        password_field.send_keys(password)

        submit_xpath = self.settings.submit_button_xpath or self.settings.next_button_xpath
        self._click_xpath(submit_xpath)
        wait.until(lambda driver: driver.current_url != self.settings.login_url)

    def open_weekly_page(self) -> None:
        self.driver.get(self.settings.weekly_page_url)

    def click_work_in(self) -> None:
        self._click_attendance_button(self.settings.work_in_xpath)

    def click_work_out(self) -> None:
        self._click_attendance_button(self.settings.work_out_xpath)

    def _click_attendance_button(self, button_xpath: str) -> None:
        if not button_xpath:
            raise AttendanceError("Attendance button XPath is not configured.")

        self.driver.get(self.settings.home_url)
        self._click_xpath(button_xpath)

        if self.settings.confirm_button_xpath:
            self._click_confirm_button(self.settings.confirm_button_xpath)

    def fetch_snapshot(self) -> AttendanceSnapshot:
        weekly_payload = self._capture_weekly_payload()
        weekly_rows = self._parse_week_rows(weekly_payload)
        today_key = datetime.today().strftime("%Y%m%d")
        today_row = next((row for row in weekly_rows if row.date == today_key), None)
        summary = build_weekly_summary(
            today=today_row,
            week_rows=weekly_rows,
            target_day=datetime.today().date(),
            weekday_target=self.settings.weekday_target_minutes,
            halfday_target=self.settings.halfday_target_minutes,
            default_start=self.settings.default_start,
            default_end=self.settings.default_end,
        )
        return AttendanceSnapshot(today=today_row, weekly_rows=weekly_rows, summary=summary)

    def _capture_weekly_payload(self) -> dict | list:
        if self.settings.weekly_page_url not in self.driver.current_url:
            self.driver.get(self.settings.weekly_page_url)
        else:
            self.driver.refresh()
        return self._capture_api_result(self.settings.weekly_data_url)

    def _click_confirm_button(self, xpath: str) -> None:
        last_error: Exception | None = None
        for delay in (0.2, 0.5, 1.0):
            try:
                time.sleep(delay)
                self._click_xpath(xpath, timeout=8)
                return
            except Exception as exc:
                last_error = exc
        raise AttendanceError(f"Could not click confirm button: {last_error}")

    def _click_xpath(self, xpath: str, timeout: int = 20) -> None:
        wait = WebDriverWait(self.driver, timeout)
        element = wait.until(EC.presence_of_element_located((By.XPATH, xpath)))
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)

        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, xpath))).click()
            return
        except (ElementClickInterceptedException, ElementNotInteractableException, TimeoutException):
            pass

        try:
            element.click()
            return
        except (ElementClickInterceptedException, ElementNotInteractableException):
            pass

        self.driver.execute_script("arguments[0].click();", element)

    def _capture_api_result(self, data_url: str) -> dict | list:
        request_map: dict[str, str] = {}

        for _ in range(80):
            logs = self.driver.get_log("performance")
            for entry in logs:
                try:
                    message = json.loads(entry["message"])["message"]
                    method = message["method"]

                    if method == "Network.requestWillBeSent":
                        request = message["params"]["request"]
                        if request.get("method") == "POST" and data_url in request.get("url", ""):
                            request_map[message["params"]["requestId"]] = request["url"]

                    if method == "Network.responseReceived":
                        request_id = message["params"]["requestId"]
                        if request_id not in request_map:
                            continue
                        body = self.driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
                        payload = json.loads(body["body"])
                        return payload.get("resultData", payload)
                except (KeyError, json.JSONDecodeError):
                    continue
            time.sleep(0.25)

        raise AttendanceError(f"Could not capture API response for {data_url}")

    def _parse_week_rows(self, payload: dict | list) -> list[DailyAttendance]:
        if not isinstance(payload, list):
            return []
        rows: list[DailyAttendance] = []
        for item in payload:
            rows.append(
                DailyAttendance(
                    date=item.get("atDt", ""),
                    label=item.get("attresultNm", ""),
                    come_time=(item.get("comeTm", "") or "")[-4:],
                    leave_time=(item.get("leaveTm", "") or "")[-4:],
                )
            )
        return rows
