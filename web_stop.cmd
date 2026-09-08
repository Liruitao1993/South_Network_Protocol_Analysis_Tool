@echo off
rem ============================================
rem  南网协议解析工具 - 停止 Web 开发服务
rem  按端口(3000/8000)找进程并结束
rem ============================================
echo Stopping web dev server (ports 3000/8000)...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 3000,8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Write-Host ('  kill PID ' + $_); Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"
echo Done.
pause
