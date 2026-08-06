@echo off
py -3 "%USERPROFILE%\.claude\hooks\handlers\builder_guard.py"
exit /b %ERRORLEVEL%
