@echo off
py -3 "%~dp0..\handlers\secret_scan.py"
exit /b %ERRORLEVEL%
