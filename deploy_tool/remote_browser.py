from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, 
                               QLineEdit, QPushButton, QLabel, QMessageBox, QHeaderView)
from PySide6.QtCore import Qt, Signal, QDateTime
from PySide6.QtGui import QIcon, QAction

# 复用 Worker 概念，但使其可独立使用或导入
from PySide6.QtCore import QThread

class BrowserWorker(QThread):
    finished = Signal(bool, object)
    
    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        
    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            if isinstance(result, tuple) and len(result) == 2:
                self.finished.emit(result[0], result[1])
            else:
                self.finished.emit(True, result)
        except Exception as e:
            self.finished.emit(False, str(e))

class RemoteFileBrowser(QDialog):
    def __init__(self, ssh_manager, initial_path="/", parent=None):
        super().__init__(parent)
        self.ssh_manager = ssh_manager
        self.current_path = initial_path
        self.setWindowTitle("远程文件浏览器")
        self.resize(800, 600)
        
        # UI 初始化
        self.layout = QVBoxLayout(self)
        
        # 顶部栏: 路径和导航
        top_layout = QHBoxLayout()
        self.up_btn = QPushButton("↑")
        self.up_btn.setFixedWidth(30)
        self.up_btn.clicked.connect(self.go_up)
        
        self.path_input = QLineEdit()
        self.path_input.setText(self.current_path)
        self.path_input.returnPressed.connect(self.reload_path)
        
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.reload_path)
        
        top_layout.addWidget(self.up_btn)
        top_layout.addWidget(self.path_input)
        top_layout.addWidget(self.refresh_btn)
        self.layout.addLayout(top_layout)
        
        # 文件列表 (树形控件)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["名称", "修改时间", "大小"])
        self.tree.setColumnWidth(0, 400)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.layout.addWidget(self.tree)
        
        # 底部栏: 操作
        bottom_layout = QHBoxLayout()
        self.status_label = QLabel("Ready")
        self.select_btn = QPushButton("选择当前目录")
        self.select_btn.setStyleSheet("background-color: #007acc; color: white; padding: 6px 15px;")
        self.select_btn.clicked.connect(self.accept)
        
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.select_btn)
        self.layout.addLayout(bottom_layout)
        
        # 初始加载
        self.load_directory(self.current_path)

    def load_directory(self, path):
        self.status_label.setText("正在加载...")
        self.tree.setEnabled(False)
        self.path_input.setText(path)
        
        self.worker = BrowserWorker(self.ssh_manager.list_remote_dir_detailed, path)
        self.worker.finished.connect(self.on_load_finished)
        self.worker.start()

    def on_load_finished(self, success, result):
        self.tree.setEnabled(True)
        if success:
            self.current_path = self.path_input.text() # Confirm path update
            self.update_tree(result)
            self.status_label.setText(f"加载完成: {len(result)} 项")
        else:
            self.status_label.setText("加载失败")
            QMessageBox.warning(self, "错误", f"无法加载目录: {result}")
            # Revert path in input if failed? 
            # self.path_input.setText(self.current_path)

    def update_tree(self, items):
        self.tree.clear()
        
        # 添加 ".."以便导航？可选，通常由“向上”按钮处理
        # 但 FinalShell 通常只是列出内容。
        
        for item in items:
            name = item['name']
            is_dir = item['is_dir']
            size = self.format_size(item['size']) if not is_dir else ""
            mtime = QDateTime.fromSecsSinceEpoch(item['mtime']).toString("yyyy-MM-dd HH:mm:ss")
            
            tree_item = QTreeWidgetItem(self.tree)
            tree_item.setText(0, name)
            tree_item.setText(1, mtime)
            tree_item.setText(2, size)
            
            # 简单的图标模拟
            if is_dir:
                tree_item.setText(0, f"📁 {name}")
                # 在 data 中存储真实名称用于逻辑处理
                tree_item.setData(0, Qt.UserRole, name)
                tree_item.setData(0, Qt.UserRole + 1, True) # Is Dir
            else:
                tree_item.setText(0, f"📄 {name}")
                tree_item.setData(0, Qt.UserRole, name)
                tree_item.setData(0, Qt.UserRole + 1, False) # Is File

    def on_item_double_clicked(self, item, column):
        is_dir = item.data(0, Qt.UserRole + 1)
        name = item.data(0, Qt.UserRole)
        
        if is_dir:
            if name == "." or name == "..": return # Should not happen usually in sftp list
            
            import posixpath
            new_path = posixpath.join(self.current_path, name)
            self.load_directory(new_path)

    def go_up(self):
        import posixpath
        parent = posixpath.dirname(self.current_path.rstrip('/'))
        if not parent: parent = '/'
        self.load_directory(parent)

    def reload_path(self):
        path = self.path_input.text().strip()
        self.load_directory(path)

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def get_selected_path(self):
        # Return the directory currently open
        return self.current_path
