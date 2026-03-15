AttendanceWidget Ubuntu Release

Build on Ubuntu:
- chmod +x build.sh
- ./build.sh

Run after build:
- ./AttendanceWidget/run.sh

What build.sh does:
- creates a local build venv under ./deploy/ubuntu/.build-venv
- installs project dependencies plus Nuitka build tools
- syncs bundled assets into ./assets
- builds a standalone Linux release under ./deploy/ubuntu/AttendanceWidget

Notes:
- Chrome or Chromium must exist on the target machine because Selenium launches the local browser.
- If python3-venv is missing, install it first with your package manager.
