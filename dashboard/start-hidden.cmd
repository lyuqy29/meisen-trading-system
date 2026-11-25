@echo off
rem ============================================================
rem  autostart entry (invoked by run-hidden.vbs at logon)
rem  runs start.cmd with a hidden console and appends output to
rem  logs\dashboard.log
rem ============================================================
setlocal
cd /d "%~dp0"
if not exist "logs" mkdir "logs"
echo.>>"logs\dashboard.log"
echo [%DATE% %TIME%] --- autostart begin --->>"logs\dashboard.log"
call "%~dp0start.cmd" >>"logs\dashboard.log" 2>&1
echo [%DATE% %TIME%] --- autostart exit %ERRORLEVEL% --->>"logs\dashboard.log"
exit /b %ERRORLEVEL%
