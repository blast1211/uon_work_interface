Attendance Widget - Ubuntu package

This package supports two ways to run:

1. Immediate local run
- Double-click AttendanceWidget.desktop
- If no binary exists yet, the launcher creates app/.venv locally and runs the app from that local runtime.
- Nothing is installed globally.

2. Real packaged app style run
- On Ubuntu, run ./build_ubuntu_binary.sh once
- This creates a standalone binary under dist/
- After that, double-click AttendanceWidget.desktop and it will launch the built binary first

Files:
- AttendanceWidget.desktop : double-click launcher
- run_attendance_widget.sh : launch script, prefers dist/AttendanceWidget.bin
- build_ubuntu_binary.sh : builds a standalone Ubuntu binary locally
- app/ : packaged application source
- koverwatch.ttf / overwatch_blue_new.png / overwatch_red_new.png : UI assets

Notes:
- A true Ubuntu binary must be built on Ubuntu, not on Windows.
- The build script installs all build dependencies into a local .build-venv folder only.
- Python 3, venv, and internet access for dependency download are needed during the first build.
