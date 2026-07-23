@echo off
cd /d "%~dp0"

python -m pip install requests pandas flask lxml

python app.py
pause
