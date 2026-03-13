# Attendance Widget App

사내 그룹웨어에 로그인해서 출근/퇴근 버튼을 누르고, 이번 주 누적 근무 시간이 기준 대비 얼마나 초과/부족한지 보여주는 데스크톱 위젯입니다.

## 기능

- Selenium으로 로그인 자동화
- 오늘 출근/퇴근 데이터 조회
- 이번 주 근태 데이터 조회 후 누적 잔여 시간 계산
- 위젯에서 `출근`, `퇴근`, `새로고침` 버튼 제공

## 빠른 시작

1. `uv sync`
2. `.env.example`을 `.env`로 복사하고 값 입력
3. `uv run attendance-widget`

## 환경 변수

- `ATTENDANCE_LOGIN_URL`
- `ATTENDANCE_HOME_URL`
- `ATTENDANCE_WEEKLY_PAGE_URL`
- `ATTENDANCE_WEEKLY_DATA_URL`
- `ATTENDANCE_TODAY_DATA_URL`
- `ATTENDANCE_USERNAME`
- `ATTENDANCE_PASSWORD`
- `ATTENDANCE_WORK_IN_XPATH`
- `ATTENDANCE_WORK_OUT_XPATH`
- `ATTENDANCE_DEFAULT_START`
- `ATTENDANCE_DEFAULT_END`

## 참고

- Chrome과 ChromeDriver 버전이 맞아야 합니다.
- 로그인 이후 화면 구조가 바뀌면 XPath와 API URL을 `.env`에서 조정하면 됩니다.
