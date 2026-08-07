@echo off
setlocal
set "DINNER_EXECUTION_MODE=direct"
claude %*
exit /b %ERRORLEVEL%
