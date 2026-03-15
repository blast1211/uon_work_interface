# Deployment

This folder contains per-platform release scripts and outputs.

- `windows/` builds a clickable `.exe` bundle on Windows.
- `ubuntu/` contains the same asset sync + build flow for Ubuntu, but it must be run on an Ubuntu machine because Linux binaries cannot be cross-built reliably from Windows.
