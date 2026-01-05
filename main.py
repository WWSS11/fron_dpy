import sys
import os
import logging
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QFileDialog, 
                               QGroupBox, QMessageBox, QProgressBar, QSplitter)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from backend import SSHManager
from remote_browser import RemoteFileBrowser  # [NEW] Import
from settings import SettingsManager  # [NEW] Import

from PySide6.QtGui import QIcon, QAction, QPalette, QColor, QFont

# --- Theme & Styles ---

def apply_dark_theme(app):
    app.setStyle("Fusion")
    
    # 调色板 (Dracula-inspired / VSCode Dark)
    dark_palette = QPalette()
    
    # 基础颜色
    color_bg = QColor(30, 30, 30)
    color_fg = QColor(220, 220, 220)
    color_alt_bg = QColor(45, 45, 45)
    color_accent = QColor(0, 122, 204)      # VSCode Blue
    color_accent_hover = QColor(0, 144, 241)
    color_red = QColor(215, 58, 73)
    
    dark_palette.setColor(QPalette.Window, color_bg)
    dark_palette.setColor(QPalette.WindowText, color_fg)
    dark_palette.setColor(QPalette.Base, color_alt_bg)
    dark_palette.setColor(QPalette.AlternateBase, color_bg)
    dark_palette.setColor(QPalette.ToolTipBase, color_fg)
    dark_palette.setColor(QPalette.ToolTipText, color_fg)
    dark_palette.setColor(QPalette.Text, color_fg)
    dark_palette.setColor(QPalette.Button, color_bg)
    dark_palette.setColor(QPalette.ButtonText, color_fg)
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, color_accent)
    dark_palette.setColor(QPalette.Highlight, color_accent)
    dark_palette.setColor(QPalette.HighlightedText, Qt.white)
    
    app.setPalette(dark_palette)
    
    # 样式表 (QSS)
    app.setStyleSheet("""
        QMainWindow {
            background-color: #1e1e1e;
        }
        QGroupBox {
            border: 1px solid #3e3e3e;
            border-radius: 6px;
            margin-top: 1.2em;
            font-weight: bold;
            color: #dcdcdc;
            padding: 10px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 5px;
            left: 10px;
            color: #569cd6; /* Blueish title */
        }
        QLineEdit {
            background-color: #2d2d2d;
            border: 1px solid #3e3e3e;
            border-radius: 4px;
            padding: 5px;
            color: #dcdcdc;
            selection-background-color: #264f78;
        }
        QLineEdit:focus {
            border: 1px solid #007acc;
        }
        QPushButton {
            background-color: #3c3c3c;
            border: 1px solid #3e3e3e;
            border-radius: 4px;
            padding: 6px 12px;
            color: #ffffff;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #4c4c4c;
        }
        QPushButton:pressed {
            background-color: #2c2c2c;
        }
        QPushButton:disabled {
            background-color: #2d2d2d;
            color: #666666;
            border: 1px solid #2d2d2d;
        }
        QComboBox {
            background-color: #2d2d2d;
            border: 1px solid #3e3e3e;
            border-radius: 4px;
            padding: 5px;
            color: #dcdcdc;
        }
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left-width: 0px;
        }
        QTextEdit {
            background-color: #1e1e1e;
            border: 1px solid #3e3e3e;
            border-radius: 4px;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 10pt;
        }
        QSplitter::handle {
            background-color: #3e3e3e;
            width: 2px;
        }
        QLabel {
            color: #cccccc;
        }
        /* 特殊按钮样式覆盖已经在代码中通过 setStyleSheet 设置的，需注意优先级 */
    """)

# --- Threads for Async Operations ---

class Worker(QThread):
    progress = Signal(str)
    finished = Signal(bool, object)  # Changed str to object to pass lists

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            # We enforce passing a 'progress_callback' to the function if it accepts it
            result = self.func(*self.args, **self.kwargs)
            # result expect to be (success, payload/message)
            if isinstance(result, tuple) and len(result) == 2:
                self.finished.emit(result[0], result[1])
            else:
                self.finished.emit(True, result)
        except Exception as e:
            self.finished.emit(False, str(e))

# --- Main GUI ---

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("前端发版与回滚工具")
        self.resize(1000, 700)
        self.ssh_manager = SSHManager()
        self.settings_manager = SettingsManager() # [NEW]
        
        # Setup Logging to GUI
        self.log_widget = QTextEdit()
        self.log_widget.setReadOnly(True)
        self.log_widget.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: Consolas;")
        
        handler = QLogHandler(self.log_widget)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger("DeployTool").setLevel(logging.INFO)
        logging.getLogger("DeployTool").addHandler(handler)
        
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.layout = QVBoxLayout(self.main_widget)

        self.setup_ui()

        # 加载保存的配置
        self.load_saved_settings() # [NEW]
        
        # State
        self.connected = False
        self.current_project_list = []

    def setup_ui(self):
        # 1. Connection Group
        conn_group = QGroupBox("服务器连接信息")
        conn_layout = QHBoxLayout()
        
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("IP Address")
        self.port_input = QLineEdit("22")
        self.port_input.setFixedWidth(50)
        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText("Username")
        self.pwd_input = QLineEdit()
        self.pwd_input.setPlaceholderText("Password")
        self.pwd_input.setEchoMode(QLineEdit.Password)
        
        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self.toggle_connection)
        
        conn_layout.addWidget(QLabel("IP:"))
        conn_layout.addWidget(self.ip_input)
        conn_layout.addWidget(QLabel("端口:"))
        conn_layout.addWidget(self.port_input)
        conn_layout.addWidget(QLabel("用户名:"))
        conn_layout.addWidget(self.user_input)
        conn_layout.addWidget(QLabel("密码:"))
        conn_layout.addWidget(self.pwd_input)
        conn_layout.addWidget(self.connect_btn)
        conn_group.setLayout(conn_layout)
        
        # 2. Path Configuration
        path_group = QGroupBox("远程路径配置")
        path_layout = QVBoxLayout()
        
        # Row 1: Project Root
        h1 = QHBoxLayout()
        self.remote_projects_path = QLineEdit("/") # Default
        self.browse_proj_btn = QPushButton("浏览...") # [NEW]
        self.browse_proj_btn.clicked.connect(lambda: self.open_remote_browser(self.remote_projects_path))
        self.browse_proj_btn.setEnabled(False) # Enable only after connect
        
        h1.addWidget(QLabel("服务器所有前端项目所在根目录:"))
        h1.addWidget(self.remote_projects_path)
        h1.addWidget(self.browse_proj_btn)
        
        # Row 2: Backup Root
        h2 = QHBoxLayout()
        self.remote_backup_path = QLineEdit("/") # Default
        self.browse_bkp_btn = QPushButton("浏览...") # [NEW]
        self.browse_bkp_btn.clicked.connect(lambda: self.open_remote_browser(self.remote_backup_path))
        self.browse_bkp_btn.setEnabled(False) 
        
        h2.addWidget(QLabel("服务器备份存放目录:"))
        h2.addWidget(self.remote_backup_path)
        h2.addWidget(self.browse_bkp_btn)
        
        self.refresh_projects_btn = QPushButton("刷新项目列表")
        self.refresh_projects_btn.clicked.connect(self.load_projects)
        self.refresh_projects_btn.setEnabled(False)
        
        path_layout.addLayout(h1)
        path_layout.addLayout(h2)
        path_layout.addWidget(self.refresh_projects_btn, alignment=Qt.AlignRight)
        path_group.setLayout(path_layout)

        # 3. Main Operation Area
        ops_splitter = QSplitter(Qt.Horizontal)
        
        # Left: Project List
        left_widget = QGroupBox("可选项目 (远程)")
        left_layout = QVBoxLayout()
        self.project_combo = QComboBox()
        self.project_combo.currentTextChanged.connect(self.check_deploy_btn_state)
        left_layout.addWidget(self.project_combo)
        left_layout.addStretch()
        left_widget.setLayout(left_layout)
        
        # Right: Actions
        right_widget = QGroupBox("操作执行")
        right_layout = QVBoxLayout()
        
        # Deploy Section
        deploy_group = QGroupBox("发版操作")
        deploy_layout = QVBoxLayout()
        
        local_file_layout = QHBoxLayout()
        self.local_path_input = QLineEdit()
        self.local_path_input.setPlaceholderText("选择本地前端包 (文件夹或 .zip)...")
        self.browse_btn = QPushButton("选择文件")
        self.browse_btn.clicked.connect(self.browse_local_file)
        
        # [NEW] 子目录选择
        self.sub_dir_input = QComboBox()
        self.sub_dir_input.setEditable(True)
        self.sub_dir_input.addItems(["dist", "html", "."])
        self.sub_dir_input.setPlaceholderText("资源子路径(如 dist)")
        self.sub_dir_input.setToolTip("如果压缩包解压后有一层文件夹(如 dist)，请在此填写，否则发布时会多一层目录。\n填 . 或 / 表示使用根目录。")
        self.sub_dir_input.setFixedWidth(100)
        
        local_file_layout.addWidget(self.local_path_input)
        local_file_layout.addWidget(QLabel("内部路径:"))
        local_file_layout.addWidget(self.sub_dir_input)
        local_file_layout.addWidget(self.browse_btn)
        
        # [NEW] 独立备份按钮
        self.backup_only_btn = QPushButton("仅备份当前版本")
        self.backup_only_btn.setStyleSheet("""
             QPushButton {
                background-color: #5cb85c;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 6px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4cae4c; }
            QPushButton:pressed { background-color: #449d44; }
            QPushButton:disabled { background-color: #444444; color: #888888; }
        """)
        self.backup_only_btn.clicked.connect(self.start_backup_only)
        self.backup_only_btn.setEnabled(False)

        self.deploy_btn = QPushButton("立即发版 (备份 -> 上传 -> 替换)")
        # 使用 QSS 中定义的 ID 选择器或类选择器会更好，这里直接设样式
        self.deploy_btn.setStyleSheet("""
            QPushButton {
                background-color: #007acc; 
                color: white; 
                font-size: 14px; 
                padding: 12px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #0098ff; }
            QPushButton:pressed { background-color: #0062a3; }
            QPushButton:disabled { background-color: #444444; color: #888888; }
        """)
        self.deploy_btn.clicked.connect(self.start_deploy)
        self.deploy_btn.setEnabled(False)
        
        deploy_layout.addLayout(local_file_layout)
        deploy_layout.addWidget(self.backup_only_btn) # Add to layout
        deploy_layout.addWidget(self.deploy_btn)
        deploy_group.setLayout(deploy_layout)
        
        # Rollback Section
        rollback_group = QGroupBox("回滚操作")
        rollback_layout = QVBoxLayout()
        
        self.view_backups_btn = QPushButton("查看该项目的所有备份")
        self.view_backups_btn.clicked.connect(self.load_backups)
        
        self.backup_combo = QComboBox()
        
        self.rollback_btn = QPushButton("回滚到选中版本")
        self.rollback_btn.setStyleSheet("""
            QPushButton {
                background-color: #d9534f;
                color: white;
                padding: 10px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #e9635f; }
            QPushButton:pressed { background-color: #c9302c; }
            QPushButton:disabled { background-color: #444444; color: #888888; }
        """)
        self.rollback_btn.clicked.connect(self.start_rollback)
        self.rollback_btn.setEnabled(False)
        
        rollback_layout.addWidget(self.view_backups_btn)
        rollback_layout.addWidget(self.backup_combo)
        rollback_layout.addWidget(self.rollback_btn)
        rollback_group.setLayout(rollback_layout)
        
        right_layout.addWidget(deploy_group)
        right_layout.addWidget(rollback_group)
        right_layout.addStretch()
        right_widget.setLayout(right_layout)
        
        ops_splitter.addWidget(left_widget)
        ops_splitter.addWidget(right_widget)
        ops_splitter.setStretchFactor(1, 2)

        # 4. Logs
        self.layout.addWidget(conn_group)
        self.layout.addWidget(path_group)
        self.layout.addWidget(ops_splitter)
        self.layout.addWidget(QLabel("操作日志:"))
        self.layout.addWidget(self.log_widget)

    def load_saved_settings(self):
        config = self.settings_manager.load_config()
        if config:
            self.ip_input.setText(config.get("ip", ""))
            self.port_input.setText(config.get("port", "22"))
            self.user_input.setText(config.get("user", ""))
            self.pwd_input.setText(config.get("pwd", ""))
            self.remote_projects_path.setText(config.get("remote_proj", "/"))
            self.remote_backup_path.setText(config.get("remote_bkp", "/"))
            
            sub_dir = config.get("default_subdir", "")
            if sub_dir:
                self.sub_dir_input.setCurrentText(sub_dir)

            self.append_log("已加载保存的连接配置。")

    # --- Actions ---

    def toggle_connection(self):
        if not self.connected:
            ip = self.ip_input.text().strip()
            port = self.port_input.text().strip()
            user = self.user_input.text().strip()
            pwd = self.pwd_input.text()
            
            if not all([ip, user, pwd]):
                QMessageBox.warning(self, "提示", "请填写完整的连接信息")
                return

            self.connect_btn.setEnabled(False)
            self.connect_thread = Worker(self.ssh_manager.connect, ip, port, user, pwd)
            self.connect_thread.finished.connect(self.on_connect_finished)
            self.connect_thread.start()
            self.append_log("正在连接服务器...")
        else:
            self.ssh_manager.close()
            self.connected = False
            self.connect_btn.setText("连接")
            self.refresh_projects_btn.setEnabled(False)
            self.browse_proj_btn.setEnabled(False)
            self.browse_bkp_btn.setEnabled(False)
            self.append_log("已断开连接")
            
    def on_connect_finished(self, success, msg):
        self.connect_btn.setEnabled(True)
        if success:
            self.connected = True
            self.connect_btn.setText("断开连接")
            self.refresh_projects_btn.setEnabled(True)
            self.browse_proj_btn.setEnabled(True) # [NEW]
            self.browse_bkp_btn.setEnabled(True)  # [NEW]
            self.append_log(f"连接成功: {msg}")
            
            # 保存配置
            self.settings_manager.save_config(
                self.ip_input.text().strip(),
                self.port_input.text().strip(),
                self.user_input.text().strip(),
                self.pwd_input.text(),
                self.remote_projects_path.text().strip(),
                self.remote_backup_path.text().strip(),
                self.sub_dir_input.currentText().strip()
            )
            self.append_log("连接配置已保存。")
            
            # 自动加载项目
            self.load_projects()
        else:
            self.append_log(f"连接失败: {msg}")
            QMessageBox.critical(self, "连接错误", msg)

    def open_remote_browser(self, target_line_edit): # [NEW] 方法
        if not self.connected: 
            return
        
        initial_path = target_line_edit.text().strip()
        browser = RemoteFileBrowser(self.ssh_manager, initial_path, self)
        
        # 执行逻辑: 模态对话框
        if browser.exec():
            selected = browser.get_selected_path()
            if selected:
                target_line_edit.setText(selected)
                self.append_log(f"选择了路径: {selected}")
                
    def load_projects(self):
        if not self.connected: return
        path = self.remote_projects_path.text()
        self.append_log(f"正在读取目录: {path}")
        
        self.list_thread = Worker(self.ssh_manager.list_projects, path)
        self.list_thread.finished.connect(self.on_list_projects_finished)
        self.list_thread.start()

    def on_list_projects_finished(self, success, result):
        if success and isinstance(result, list):
            self.project_combo.clear()
            self.project_combo.addItems(result)
            self.append_log(f"获取到 {len(result)} 个项目")
        else:
            self.append_log(f"获取项目列表失败: {result}")

    def browse_local_file(self):
        # 弹出一个菜单让用户选择是“文件夹”还是“Zip压缩包”
        # 或者直接使用 FileDialog 同时过滤
        # Qt 的 getOpenFileName 和 getExistingDirectory 是分开的。
        # 这里用一个简单的逻辑：优先尝试选择文件，如果取消了，或者用户想选文件夹... 
        # 为了体验好，不如增加一个下拉菜单在按钮上，或者是弹出询问。
        # 简单方案: 默认选文件(zip)，如果想选文件夹需要...
        # 完美方案: 使用 QFileDialog 自定义，但比较麻烦。
        # 折中方案: 弹出一个小菜单。
        
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        action_zip = menu.addAction("选择 ZIP 压缩包")
        action_dir = menu.addAction("选择 文件夹")
        
        # 显示在按钮位置
        action = menu.exec(self.browse_btn.mapToGlobal(self.browse_btn.rect().bottomLeft()))
        
        if action == action_zip:
            file_path, _ = QFileDialog.getOpenFileName(self, "选择压缩包", "", "Zip Files (*.zip)")
            if file_path:
                self.local_path_input.setText(file_path)
                self.check_deploy_btn_state()
        elif action == action_dir:
            directory = QFileDialog.getExistingDirectory(self, "选择前端项目文件夹")
            if directory:
                self.local_path_input.setText(directory)
                self.check_deploy_btn_state()

    def check_deploy_btn_state(self):
        has_project = bool(self.project_combo.currentText())
        has_local = bool(self.local_path_input.text())
        
        # Deploy 需要项目 + 本地文件 + 连接
        self.deploy_btn.setEnabled(has_project and has_local and self.connected)
        
        # View Backups 和 Backup Only 只需要项目 + 连接
        self.view_backups_btn.setEnabled(has_project and self.connected)
        self.backup_only_btn.setEnabled(has_project and self.connected) # [NEW]

    def start_deploy(self):
        project = self.project_combo.currentText()
        local_path = self.local_path_input.text()
        remote_root = self.remote_projects_path.text()
        backup_root = self.remote_backup_path.text()

        if not project or not local_path: return
        
        # 获取子路径设置 (默认为空或用户输入)
        sub_dir = self.sub_dir_input.currentText().strip()
        if sub_dir in [".", "/"]: sub_dir = "" # 处理根目录标识
        
        reply = QMessageBox.question(self, "确认发版", 
                                     f"确定要发布项目 [{project}] 吗？\n\n1. 本地源: [{local_path}]\n2. 子资源路径: [{sub_dir if sub_dir else '(根目录)'}]\n3. 自动解压(若是ZIP)并备份覆盖。",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes: return

        self.append_log(f"=== 开始发布 {project} ===")
        self.set_ui_busy(True)
        
        def deploy_pipeline():
            import shutil
            import tempfile
            import zipfile
            
            # 0. 预处理: 解压与路径调整
            self.append_log("步骤 0/3: 准备本地文件...")
            deploy_source_path = local_path
            temp_extract_dir = None
            
            try:
                # 如果是 ZIP 文件
                if os.path.isfile(local_path) and local_path.lower().endswith('.zip'):
                    self.append_log(f"正在解压 {os.path.basename(local_path)}...")
                    temp_extract_dir = tempfile.mkdtemp()
                    with zipfile.ZipFile(local_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_extract_dir)
                    deploy_source_path = temp_extract_dir
                
                # 处理子路径 (例如 dist)
                if sub_dir:
                    potential_path = os.path.join(deploy_source_path, sub_dir)
                    if os.path.exists(potential_path) and os.path.isdir(potential_path):
                        deploy_source_path = potential_path
                        self.append_log(f"定位到子目录: {sub_dir}")
                    else:
                        # 只有当用户显式指定了子路径，且该路径不存在时才报错
                        # 如果是解压后的根目录，可能结构不一样，提示用户
                        msg = f"未在包中找到子目录: {sub_dir}"
                        return False, msg

                # 1. 备份
                self.append_log("步骤 1/3: 创建服务器备份...")
                ok, msg = self.ssh_manager.backup_project(remote_root, project, backup_root)
                if not ok: return False, msg
                self.append_log(msg)
                
                # 2. 部署
                self.append_log("步骤 2/3: 上传并部署...")
                ok, msg = self.ssh_manager.deploy_project(deploy_source_path, remote_root, project, 
                                                          progress_callback=lambda m: print(m))
                return ok, msg
                
            except Exception as e:
                return False, f"本地处理出错: {str(e)}"
            finally:
                # 清理临时文件
                if temp_extract_dir and os.path.exists(temp_extract_dir):
                    try:
                        shutil.rmtree(temp_extract_dir)
                    except:
                        pass

        self.deploy_thread = Worker(deploy_pipeline)
        self.deploy_thread.finished.connect(self.on_deploy_finished)
        self.deploy_thread.start()

    def on_deploy_finished(self, success, msg):
        self.set_ui_busy(False)
        if success:
            self.append_log(f"发布成功! {msg}")
            QMessageBox.information(self, "成功", "发布流程执行完成")
        else:
            self.append_log(f"发布失败: {msg}")
            QMessageBox.critical(self, "错误", f"发布过程中止: {msg}")

    def start_backup_only(self):
        project = self.project_combo.currentText()
        remote_root = self.remote_projects_path.text()
        backup_root = self.remote_backup_path.text()
        
        if not project: return
        
        self.set_ui_busy(True)
        self.append_log(f"=== 开始备份 {project} ===")
        
        # 直接复用 ssh_manager.backup_project
        self.backup_op_thread = Worker(self.ssh_manager.backup_project, remote_root, project, backup_root)
        self.backup_op_thread.finished.connect(self.on_backup_only_finished)
        self.backup_op_thread.start()
        
    def on_backup_only_finished(self, success, msg):
        self.set_ui_busy(False)
        if success:
            self.append_log(msg)
            QMessageBox.information(self, "备份成功", f"备份已完成。\n{msg}")
        else:
            self.append_log(f"备份失败: {msg}")
            QMessageBox.critical(self, "备份失败", msg)

    def load_backups(self):
        project = self.project_combo.currentText()
        if not project: return
        
        backup_root = self.remote_backup_path.text()
        self.append_log(f"正在查询项目 [{project}] 的备份...")
        
        self.backup_thread = Worker(self.ssh_manager.list_backups, backup_root, project)
        self.backup_thread.finished.connect(self.on_load_backups_finished)
        self.backup_thread.start()

    def on_load_backups_finished(self, success, result):
        if success and isinstance(result, list):
            self.backup_combo.clear()
            self.backup_combo.addItems(result)
            self.append_log(f"找到 {len(result)} 个备份")
            if result:
                self.rollback_btn.setEnabled(True)
            else:
                self.rollback_btn.setEnabled(False)
        else:
            self.append_log("获取备份列表失败")

    def start_rollback(self):
        project = self.project_combo.currentText()
        backup = self.backup_combo.currentText()
        remote_root = self.remote_projects_path.text()
        backup_root = self.remote_backup_path.text()
        
        if not project or not backup: return
        
        reply = QMessageBox.warning(self, "确认回滚", 
                                    f"⚠️ 警告: 确定要将 [{project}] 回滚到备份 [{backup}] 吗？\n当前运行的版本将被覆盖！",
                                    QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes: return

        self.set_ui_busy(True)
        self.append_log(f"=== 开始回滚 {project} -> {backup} ===")
        
        backup_full_path = f"{backup_root}/{backup}"
        target_full_path = f"{remote_root}/{project}"
        
        self.rollback_thread = Worker(self.ssh_manager.rollback_project, backup_full_path, target_full_path)
        self.rollback_thread.finished.connect(self.on_rollback_finished)
        self.rollback_thread.start()
        
    def on_rollback_finished(self, success, msg):
        self.set_ui_busy(False)
        if success:
            self.append_log(f"回滚成功")
            QMessageBox.information(self, "成功", "回滚操作完成")
        else:
            self.append_log(f"回滚失败: {msg}")
            QMessageBox.critical(self, "错误", msg)

    def set_ui_busy(self, busy):
        self.deploy_btn.setEnabled(not busy)
        self.rollback_btn.setEnabled(not busy)
        self.connect_btn.setEnabled(not busy)
        self.backup_only_btn.setEnabled(not busy) # [NEW]
        # 我们不禁用所有内容，只禁用关键操作

    def append_log(self, text):
        self.log_widget.append(text)

class QLogHandler(logging.Handler):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def emit(self, record):
        msg = self.format(record)
        # 线程安全问题? 在 PySide 中，GUI 更新必须发生在主线程上。
        # 但这里我们简化了。如果复杂，请使用 Signal。
        # 目前，我们假设如果从线程直接追加可能会崩溃。
        # 所以我们应该严格使用 Signal 从线程记录日志。
        # MainWindow.append_log 可以安全地从 MainWindow 方法调用，
        # 但如果从后端调用，则有风险。
        # 通过信号重新路由所有日志更安全，但目前只需坚持从 Worker 返回消息。
        pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 可选: 应用暗黑主题或样式
    # app.setStyle("Fusion") # Moved inside apply_dark_theme
    apply_dark_theme(app)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
