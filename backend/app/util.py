
from pathlib import Path
import shutil


def make_dir(dir_path: str|Path, re_create: bool=True):
    target_dir = Path(dir_path)
    
    if target_dir.exists() and re_create:
        # 如果存在，使用 rmtree 递归删除该文件夹及其内部的所有子文件和子文件夹
        shutil.rmtree(target_dir)
        
    # 重新创建这个文件夹
    # parents=True: 如果上级目录不存在，会自动连同上级目录一起创建
    # exist_ok=True: 防御性参数，防止高并发下创建瞬间冲突报错
    target_dir.mkdir(parents=True, exist_ok=True)