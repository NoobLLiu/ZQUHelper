@echo off
rem ZQUHelper server launcher (start by double-click)
cd /d %~dp0
go run ./cmd/server
pause
