# Frontend Deployment Tool (Python GUI)

一个基于 Python (PySide6) 和 Paramiko 的前端项目自动化部署工具。
支持 SSH/SFTP 连接、多项目管理、zip 压缩包上传、自动解压、备份与回滚等功能。

## 功能特性

*   **多环境/多项目支持**: 自动读取远程目录下的项目列表。
*   **拖拽式上传**: 支持选择本地文件夹或 `.zip` 压缩包。
*   **自动化部署流程**:
    *   **备份**: 自动将旧版本打包为 `.tar.gz` 存档。
    *   **保留配置**: 自动识别并保留远程的 `config.json` 文件（不覆盖）。
    *   **替换**: 安全替换项目文件。
*   **一键回滚**: 支持选择历史备份版本进行解压回滚。
*   **独立备份**: 支持仅备份不发版。
*   **安全存储**: 自动保存连接信息，密码采用本地密钥加密存储。
*   **暗色主题**: 内置现代化的暗色 UI 主题。

## 目录结构

```text
fron_dpy/
├── run.py                  # 启动入口脚本
├── build.bat               # Nuitka 打包脚本 (Windows)
├── requirements.txt        # Python 依赖
├── deploy_tool/            # 核心代码包
│   ├── main.py             # GUI 主窗口逻辑
│   ├── backend.py          # SSH/SFTP 后端逻辑
│   ├── remote_browser.py   # 远程文件浏览器组件
│   └── settings.py         # 配置存取与加密逻辑
├── app_config.json         # (运行后生成) 只有连接配置
└── secret.key              # (运行后生成) 本地加密密钥
```

## 开发与运行

### 1. 安装依赖

需安装 Python 3.10+。

```bash
pip install -r requirements.txt
```

### 2. 运行

```bash
python run.py
```

### 3. 打包 (Windows EXE)

本项目已配置 Nuitka 构建脚本。

1.  确保已安装 C 编译器 (VS 2022 Build Tools 或 MinGW64)。
2.  运行构建脚本：

```powershell
.\build.bat
```

构建完成后，可执行文件将生成在 `dist/FronDeployTool.exe`。

## 注意事项

*   **config.json 保留逻辑**: 部署时默认会尝试从旧版中提取 `config.json` 并覆盖到新版中。这适用于前端项目有环境配置文件的情况。
*   **备份路径**: 请确保远程服务器上的备份路径对应的磁盘空间充足。
