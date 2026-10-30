@echo off
setlocal
python -X utf8 "%~dp0etm-service\trace.py" %*
exit /b %errorlevel%
