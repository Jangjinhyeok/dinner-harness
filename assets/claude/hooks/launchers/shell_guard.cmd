@echo off
py -3 "%~dp0..\handlers\shell_guard.py"
exit /b %ERRORLEVEL%
