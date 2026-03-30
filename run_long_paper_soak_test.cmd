@echo off
setlocal
powershell -ExecutionPolicy Bypass -File "%~dp0run_long_paper_soak_test.ps1" %*
endlocal
