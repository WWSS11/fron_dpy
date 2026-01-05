import os
import posixpath
import paramiko
import time
import logging
from stat import S_ISDIR

class SSHManager:
    def __init__(self):
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.sftp = None
        self.logger = logging.getLogger("DeployTool")

    def connect(self, hostname, port, username, password):
        try:
            self.client.connect(hostname, port=int(port), username=username, password=password, timeout=10)
            self.sftp = self.client.open_sftp()
            return True, "连接成功"
        except Exception as e:
            return False, str(e)

    def close(self):
        if self.sftp:
            self.sftp.close()
        if self.client:
            self.client.close()

    def run_command(self, command):
        """运行命令并返回标准输出/标准错误"""
        self.logger.info(f"Executing: {command}")
        stdin, stdout, stderr = self.client.exec_command(command)
        out = stdout.read().decode('utf-8').strip()
        err = stderr.read().decode('utf-8').strip()
        if out:
            self.logger.info(f"STDOUT: {out}")
        if err:
            self.logger.error(f"STDERR: {err}")
        return out, err

    def list_projects(self, remote_path):
        """列出远程路径下的目录"""
        try:
            if not remote_path.endswith('/'):
                remote_path += '/'
            
            cmd = f"ls -F {remote_path} | grep /$"
            out, err = self.run_command(cmd)
            
            if err and "No such file" in err:
                return False, f"目录不存在: {err}"
            elif err:
                 # 可疑的 stderr，但检查是否有输出
                 if not out:
                     return False, f"列出目录失败: {err}"
            
            projects = [p.strip('/') for p in out.splitlines()]
            return True, projects
        except Exception as e:
            self.logger.error(f"Error listing projects: {e}")
            return False, str(e)

    def list_remote_dir_detailed(self, remote_path):
        """
        使用 SFTP 列出包含属性的目录内容。
        返回: (bool, list_of_dicts)
        每个字典: {'name': str, 'is_dir': bool, 'size': int, 'mtime': int, 'attr': SFTPAttributes}
        """
        try:
            if not self.sftp:
                return False, "SFTP 未连接"
            
            # 确保路径有效 (简单检查)
            if not remote_path: remote_path = '.'
            
            file_list = []
            # listdir_attr 返回 SFTPAttributes 对象
            items = self.sftp.listdir_attr(remote_path)
            
            # 排序: 目录在前，然后是文件。两者均按字母顺序。
            items.sort(key=lambda x: (not S_ISDIR(x.st_mode), x.filename))

            for item in items:
                is_dir = S_ISDIR(item.st_mode)
                file_list.append({
                    'name': item.filename,
                    'is_dir': is_dir,
                    'size': item.st_size,
                    'mtime': item.st_mtime,
                    # 格式化的时间字符串可以在此处添加，也可以在 UI 中添加
                })
            return True, file_list
        except Exception as e:
            self.logger.error(f"Error listing detailed dir {remote_path}: {e}")
            return False, str(e)

    def list_backups(self, backup_dir, project_name):
        """列出特定项目的备份"""
        try:
            cmd = f"ls -1 {backup_dir} | grep '^{project_name}_'"
            out, err = self.run_command(cmd)
            if err:
                return []
            return sorted(out.splitlines(), reverse=True) # 最新的在前
        except Exception as e:
            self.logger.error(f"Error listing backups: {e}")
            return []

    def backup_project(self, remote_projects_dir, project_name, backup_dir):
        """备份逻辑: tar -czf 打包"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        # 确保路径不以 / 结尾以便于 dirname/basename 处理，但在 posixpath.join 中通常没问题
        # source_full = path/to/project
        # parent = path/to
        
        # 规范化路径
        if remote_projects_dir.endswith('/'): remote_projects_dir = remote_projects_dir[:-1]
        
        source_full = posixpath.join(remote_projects_dir, project_name)
        dest_name = f"{project_name}_{timestamp}.tar.gz"
        dest_full = posixpath.join(backup_dir, dest_name)

        # 检查源是否存在
        check_cmd = f"[ -d '{source_full}' ] && echo 'exists'"
        out, _ = self.run_command(check_cmd)
        if out != 'exists':
            return False, f"项目目录不存在: {source_full}"

        # 确保备份目录存在
        self.run_command(f"mkdir -p {backup_dir}")

        # 使用 tar -czf 目标文件 -C 父目录 项目名
        # 这样压缩包内的顶层就是一个文件夹，解压时不会散乱
        cmd = f"tar -czf '{dest_full}' -C '{remote_projects_dir}' '{project_name}'"
        out, err = self.run_command(cmd)
        
        # tar 在某些警告下也会输出 stderr，但通常成功退出码为0。
        # Paramiko exec_command 不直接给出退出码，需要配合 check。
        # 这里简单依赖 err 为空或特定成功标识。
        # 更好的做法是 cmd = "... && echo success"
        
        # 再次检查文件是否生成
        check_file = f"[ -f '{dest_full}' ] && echo 'created'"
        out_check, _ = self.run_command(check_file)
        
        if out_check == 'created':
            return True, f"备份成功: {dest_name}"
        else:
            return False, f"备份失败: {err}"

    def deploy_project(self, local_path, remote_projects_dir, project_name, progress_callback=None):
        """
        部署逻辑:
        1. 上传 local_path 到 /tmp/<project_name>_new
        2. 将 config.json 从现有项目复制到 /tmp/<project_name>_new/config.json
        3. 删除现有项目内容
        4. 将 /tmp/<project_name>_new 内容移动到现有项目
        """
        try:
            temp_remote_dir = f"/tmp/{project_name}_new_{int(time.time())}"
            target_project_path = posixpath.join(remote_projects_dir, project_name)
            
            # 1. 上传
            if progress_callback: progress_callback("正在上传新版本...")
            self.upload_dir(local_path, temp_remote_dir)

            # 2. 保留配置
            if progress_callback: progress_callback("正在保留配置...")
            # 检查目标中是否存在 config.json
            config_path = posixpath.join(target_project_path, "config.json")
            check_config = f"[ -f '{config_path}' ] && echo 'yes'"
            out, _ = self.run_command(check_config)
            
            if out == 'yes':
                # 将配置从目标复制到临时目录
                cmd = f"cp -f '{config_path}' '{posixpath.join(temp_remote_dir, 'config.json')}'"
                self.run_command(cmd)
            else:
                self.logger.warning("目标项目没有 config.json，跳过保留配置步骤")

            # 3. & 4. 替换
            if progress_callback: progress_callback("正在替换文件...")
            
            # 确保目标目录存在 (如果是新项目)
            self.run_command(f"mkdir -p '{target_project_path}'")
            
            # 清理目标
            rm_cmd = f"rm -rf '{target_project_path}'/*"  # 如果路径是根目录则很危险!!!
            if len(target_project_path) < 5:
                return False, "目标路径太短，拒绝执行危险操作"
                
            self.run_command(rm_cmd)
            
            # 从临时目录移动到目标
            mv_cmd = f"cp -r '{temp_remote_dir}'/* '{target_project_path}'/"
            out, err = self.run_command(mv_cmd)
            if err:
                return False, f"部署文件移动失败: {err}"
                
            # 清理临时目录
            self.run_command(f"rm -rf '{temp_remote_dir}'")
            
            return True, "发布完成"

        except Exception as e:
            return False, f"发布过程出错: {e}"

    def upload_dir(self, local_dir, remote_dir):
        """递归上传目录"""
        try:
            self.run_command(f"mkdir -p '{remote_dir}'")
            for root, dirs, files in os.walk(local_dir):
                rel_path = os.path.relpath(root, local_dir)
                remote_root = posixpath.join(remote_dir, rel_path.replace('\\', '/'))
                
                # 创建远程子目录
                for d in dirs:
                    self.run_command(f"mkdir -p '{posixpath.join(remote_root, d)}'")
                
                # 上传文件
                for f in files:
                    local_file = os.path.join(root, f)
                    remote_file = posixpath.join(remote_root, f)
                    self.sftp.put(local_file, remote_file)
        except Exception as e:
            raise e

    def rollback_project(self, backup_path_tar, target_project_path):
        """
        回滚逻辑:
        1. 清理目标
        2. 解压备份 (tar -xzf)
        """
        if len(target_project_path) < 5:
            return False, "目标路径太短，拒绝执行危险操作"

        # 校验备份文件是否以 .tar.gz 结尾 (简单校验)
        # 其实不强制，只要是 tar 包即可，但符合我们生成规则
        
        # 1. 清理
        cmd_clean = f"rm -rf '{target_project_path}'" # 我们删掉整个文件夹，因为 tar 解压会带文件夹头
        # 稍微危险，需要确认 parent
        parent_dir = posixpath.dirname(target_project_path)
        project_dirname = posixpath.basename(target_project_path)
        
        # 这里为了安全，我们还是清空内容吧，但是 tar -C parent 可能会解压出 proj_name 目录
        # 如果 proj_name 目录已存在，tar 通常会覆盖其中的文件。
        # 为了干净的回滚（删除新版增加的文件），最好是 rm -rf target_project_path
        
        # 检查 parent 是否存在
        if not parent_dir: return False, "无法确定父目录"
        
        self.run_command(f"rm -rf '{target_project_path}'")
        
        # 2. 解压
        # tar -xzf backup.tar.gz -C /path/to/parent
        cmd_restore = f"tar -xzf '{backup_path_tar}' -C '{parent_dir}'"
        out, err = self.run_command(cmd_restore)
        
        # 再次确认
        check_exist = f"[ -d '{target_project_path}' ] && echo 'ok'"
        out_check, _ = self.run_command(check_exist)
        
        if out_check == 'ok':
            return True, "回滚成功"
        else:
             return False, f"回滚失败 (解压错误?): {err}"
