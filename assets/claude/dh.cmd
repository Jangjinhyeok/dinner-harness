@echo off
setlocal
set "DINNER_EXECUTION_MODE=builder-first"
claude %*
exit /b %ERRORLEVEL%
