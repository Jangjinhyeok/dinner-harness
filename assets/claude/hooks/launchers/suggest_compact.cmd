@echo off
py -3 "%USERPROFILE%\.claude\hooks\handlers\suggest_compact.py"
exit /b %ERRORLEVEL%
