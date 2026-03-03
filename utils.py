# utils.py
import sys
import os
import platform
import shutil
from PyQt6.QtGui import QIcon

APP_NAME = "LifeQuest"

class PathManager:
    @staticmethod
    def get_data_dir():
        """获取用户数据存储目录 (存档/配置)"""
        if platform.system() == "Windows":
            base_path = os.getenv("APPDATA")
        else:
            base_path = os.path.expanduser("~")
        
        # 最终路径: C:\Users\YourName\AppData\Roaming\LifeQuest
        data_dir = os.path.join(base_path, APP_NAME)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        return data_dir

    @staticmethod
    def get_resource_path(relative_path):
        """获取资源文件路径 (图标/音频)，支持 PyInstaller 打包后的临时目录"""
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller 打包后的临时目录
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), relative_path)

    @staticmethod
    def get_config_path():
        return os.path.join(PathManager.get_data_dir(), "config.json")

    @staticmethod
    def get_db_path():
        return os.path.join(PathManager.get_data_dir(), "lifequest.db")

def set_app_icon(app, icon_name="app.ico"):
    """设置任务栏图标 (解决 Windows 下任务栏显示默认图标的问题)"""
    icon_path = PathManager.get_resource_path(icon_name)
    if os.path.exists(icon_path):
        icon = QIcon(icon_path)
        app.setWindowIcon(icon)
        
        # Windows 特有：设置 App ID 以便任务栏识别
        if platform.system() == "Windows":
            import ctypes
            myappid = f'mycompany.{APP_NAME}.v3.1' 
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)