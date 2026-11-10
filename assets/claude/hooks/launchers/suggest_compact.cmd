@echo off
py -3 "%~dp0..\handlers\suggest_compact.py"
exit /b %ERRORLEVEL%
