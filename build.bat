@echo off
chcp 65001 >nul
echo ========================================================
echo       构建成exe文件
echo ========================================================
echo.
echo 安装Nuitka和依赖...
pip install nuitka zstandard

echo.
echo 清理之前的构建...
rmdir /s /q dist
rmdir /s /q build
rmdir /s /q main.dist
rmdir /s /q main.build
rmdir /s /q main.onefile-build

echo.
echo Compiling with Nuitka (This may take a few minutes)...
echo Mode: Onefile (Single Exe), No Console, PySide6 Plugin enabled.
echo.

nuitka --standalone --onefile ^
    --enable-plugin=pyside6 ^
    --windows-console-mode=disable ^
    --output-dir=dist ^
    --mingw64 ^
    --assume-yes-for-downloads ^
    --output-filename=FronDeployTool.exe ^
    --company-name="Private" ^
    --product-name="Frontend Deployment Tool" ^
    --file-version=1.0.0.0 ^
    --copyright="Copyright (c) 2025" ^
    main.py

echo.
if %errorlevel% neq 0 (
    echo Build FAILED! Please checks errors above.
    pause
    exit /b %errorlevel%
)

echo.
echo ========================================================
echo       构建成功
echo       文件存放在: dist\FronDeployTool.exe
echo ========================================================
pause
