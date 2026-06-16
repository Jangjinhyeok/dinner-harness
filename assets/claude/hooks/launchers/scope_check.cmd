@echo off
py -3 "%USERPROFILE%\.claude\hooks\handlers\scope_check.py"
exit /b %ERRORLEVEL%
