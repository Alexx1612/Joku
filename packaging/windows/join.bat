@echo off
rem Join a co-op game:  join.bat <host-address> <YourName>
set HOST=%1
set NAME=%2
if "%HOST%"=="" set /p HOST=Host address (127.0.0.1 if the server is on this PC): 
if "%NAME%"=="" set /p NAME=Your name: 
"%~dp0RealmReforged-CoopClient.exe" --host %HOST% --name %NAME%
pause
