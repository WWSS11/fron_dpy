import os
import json
import base64
from cryptography.fernet import Fernet

class SettingsManager:
    def __init__(self, config_file="app_config.json", key_file="secret.key"):
        self.config_file = config_file
        self.key_file = key_file
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)

    def _load_or_create_key(self):
        if os.path.exists(self.key_file):
            with open(self.key_file, "rb") as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, "wb") as f:
                f.write(key)
            return key

    def encrypt(self, text):
        if not text: return ""
        return self.cipher.encrypt(text.encode()).decode()

    def decrypt(self, text):
        if not text: return ""
        try:
            return self.cipher.decrypt(text.encode()).decode()
        except Exception:
            return ""

    def save_config(self, ip, port, user, pwd, remote_proj, remote_bkp, default_subdir="dist"):
        data = {
            "ip": ip,
            "port": port,
            "user": user,
            "pwd": self.encrypt(pwd),
            "remote_proj": remote_proj,
            "remote_bkp": remote_bkp,
            "default_subdir": default_subdir
        }
        with open(self.config_file, "w", encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    def load_config(self):
        if not os.path.exists(self.config_file):
            return None
        
        try:
            with open(self.config_file, "r", encoding='utf-8') as f:
                data = json.load(f)
            
            # Decrypt password
            if "pwd" in data:
                data["pwd"] = self.decrypt(data["pwd"])
            
            return data
        except Exception as e:
            print(f"Failed to load config: {e}")
            return None
