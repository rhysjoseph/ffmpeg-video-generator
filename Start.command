#!/bin/zsh
set -e
cd -- "${0:A:h}"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  print 'FFmpeg is required. Install Homebrew, then run: brew install ffmpeg'
  read '?Press Return to close.'
  exit 1
fi
if [[ -x .venv/bin/python3 ]]; then
  runtime=.venv/bin/python3
elif python3 -c 'import PIL' >/dev/null 2>&1; then
  runtime=python3
else
  python3 -m venv .venv
  .venv/bin/python3 -m pip install -r requirements.txt
  runtime=.venv/bin/python3
fi
print 'Open http://localhost:9191 in your browser.'
exec "$runtime" app.py
