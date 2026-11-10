@echo off
py -3 "%~dp0..\handlers\scope_check.py"
exit /b %ERRORLEVEL%
