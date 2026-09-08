@echo off
rem ===================================================
rem  南网协议解析工具 - Web 版开发服务启动
rem  前端 http://localhost:3000  后端 http://localhost:8000
rem  停止：本窗口按 Ctrl+C，或双击 web_stop.cmd
rem ===================================================
cd /d "%~dp0reflex_web"
set PYTHONUTF8=1
echo Web dev server starting...  frontend :3000  backend :8000
python -m reflex run --frontend-port 3000 --backend-port 8000
pause
