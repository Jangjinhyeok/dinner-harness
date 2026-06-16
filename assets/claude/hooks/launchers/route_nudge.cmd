@echo off
py -3 "%USERPROFILE%\.claude\hooks\handlers\route_nudge.py"
exit /b %ERRORLEVEL%
