@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 找不到 python，请先安装 Python 3.10+ 并加入 PATH。
  pause
  exit /b 1
)
python -c "import flask, usb.core, elftools, capstone, numpy" >nul 2>nul
if errorlevel 1 (
  echo 正在安装依赖（Flask / pyusb / pyelftools / capstone / numpy）…
  python -m pip install -r requirements.txt
  if errorlevel 1 ( echo [错误] 依赖安装失败。 & pause & exit /b 1 )
)
echo ETM 本地服务：http://127.0.0.1:8766/
echo 工具箱 ETM 页会 iframe 这个地址；也可以直接打开。
python server.py --port 8766
pause
