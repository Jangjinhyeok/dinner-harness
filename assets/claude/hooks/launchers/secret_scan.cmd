@echo off
py -3 "%USERPROFILE%\.claude\hooks\handlers\secret_scan.py"
exit /b %ERRORLEVEL%
