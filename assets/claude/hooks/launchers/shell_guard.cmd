@echo off
py -3 "%USERPROFILE%\.claude\hooks\handlers\shell_guard.py"
exit /b %ERRORLEVEL%
