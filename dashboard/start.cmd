@echo off
rem ============================================================
rem  liuliu-trading-system dashboard -- Windows launcher
rem  (Windows counterpart of start.sh; keep this file ASCII + CRLF)
rem  usage:  start.cmd
rem          set PORT=9000 ^&^& start.cmd
rem ============================================================
setlocal
cd /d "%~dp0"
if not defined PORT set "PORT=8777"

rem 0) already serving? then stay quiet (keeps the logon task idempotent)
powershell -NoProfile -Command "try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',%PORT%);exit 0}catch{exit 1}" >nul 2>&1
if not errorlevel 1 (
  echo [i] already running: http://127.0.0.1:%PORT%
  exit /b 0
)

rem 1) explicit DSH_PYTHON wins
set "PY="
if defined DSH_PYTHON if exist "%DSH_PYTHON%" set "PY=%DSH_PYTHON%"

rem 2) DSH bundled runtime: %USERPROFILE%\.dsh\dsh-runtimes\*\dependencies\python\python.exe
if not defined PY (
  for /d %%D in ("%USERPROFILE%\.dsh\dsh-runtimes\*") do (
    if not defined PY if exist "%%D\dependencies\python\python.exe" set "PY=%%D\dependencies\python\python.exe"
  )
)

rem 3) system python
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo [x] Python 3 not found. Set DSH_PYTHON to python.exe and retry. 1>&2
  exit /b 1
)

set "PYTHONIOENCODING=utf-8"
echo liuliu trading dashboard
echo   Python: %PY%
echo   URL:    http://127.0.0.1:%PORT%
echo   (Ctrl+C to stop)
%PY% -u server.py
