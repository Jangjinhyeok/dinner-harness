@echo off
py -3 "%USERPROFILE%\.claude\hooks\handlers\learning_log.py"
exit /b %ERRORLEVEL%
