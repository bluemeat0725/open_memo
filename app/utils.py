import uuid
import configparser
from pathlib import Path
import os

# 项目根目录
PROJECT_ROOT = Path("project_dir")
if not PROJECT_ROOT.exists():
    PROJECT_ROOT.mkdir(exist_ok=True)

def load_projects():
    """扫描并加载所有项目"""
    projects = []
    for project_dir in PROJECT_ROOT.iterdir():
        if project_dir.is_dir():
            config_file = project_dir / "config.conf"
            if config_file.exists():
                config = configparser.ConfigParser()
                config.read(config_file, encoding="utf-8")
                project_info = {
                    "name": config.get("info", "name").strip("'"),
                    "id": project_dir.name,
                    "path": str(project_dir)
                }
                projects.append(project_info)
    return projects

def load_project(id):
    project_dir = PROJECT_ROOT / id
    if project_dir.exists():
        config_file = project_dir / "config.conf"
        memo_file = Path(project_dir) / "memo.txt"
        memo=''
        if os.path.exists(memo_file):
            with open(memo_file, "r", encoding='utf8') as f:
                    memo = f.read()
        
        if config_file.exists():
            config = configparser.ConfigParser()
            config.read(config_file, encoding="utf-8")
            memo_stat=config.get('info','memo_stat')
            if memo_stat=='1' and memo:
                memo_stat='0'
                config['info']['memo_stat']=memo_stat
                with open(project_dir / "config.conf", "w", encoding="utf-8") as f:
                    config.write(f)
                
            project_info = {
                "name": config.get("info", "name").strip("'"),
                "person_name":config.get("info", "person_name").strip("'"),
                "id": project_dir.name,
                "path": str(project_dir),
                "memo_stat":memo_stat,
                "memo":memo,
                "files": {},
                "stories":{}
            }
            
            
            # 加载文件信息
            if "files" in config:
                import ast
                for file_id, file_info_str in config["files"].items():
                    file_info = ast.literal_eval(file_info_str)
                    project_info["files"][file_id] = file_info
                    transcribe=''
                    transcribe_file_path = Path(project_dir) / f"{file_id}.txt"
                    if os.path.exists(transcribe_file_path):
                        with open(project_dir / f"{file_id}.txt", "r", encoding='utf8') as f:
                            transcribe = f.read()
                    project_info["files"][file_id]["transcribe"] = transcribe  
                    if transcribe:
                        project_info["files"][file_id]["status"] = '1'
                        # 更新配置文件中的status
                        config_str = config["files"][file_id]
                        file_info = ast.literal_eval(config_str)
                        file_info["status"] = '1'
                        config["files"][file_id] = str(file_info)
                        with open(project_dir / "config.conf", "w", encoding="utf-8") as f:
                            config.write(f)
            # print(project_info)
            return project_info

def create_project(project_name, person_name):
    """创建新项目"""
    project_id = str(uuid.uuid4())[:8]
    project_path = PROJECT_ROOT / project_id
    project_path.mkdir(exist_ok=True)
    
    # 创建配置文件
    config = configparser.ConfigParser()
    config["info"] = {"name": project_name,"person_name":person_name,"memo_stat":"0"}
    config["files"] = {}
    config["stories"] = {}
    
    with open(project_path / "config.conf", "w", encoding='utf-8') as f:  # 添加 UTF-8 编码
        config.write(f)
    
    project_info = {
        "name": project_name,
        "person_name":person_name,
        "id": project_id,
        "path": str(project_path),
        "memo_stat": "0",
        "files": {}
    }
    return project_info

def update_project_name(project, new_name, person_name):
    """更新项目名称"""
    config_file = Path(project['path']) / "config.conf"
    config = configparser.ConfigParser()
    config.read(config_file, encoding="utf-8")
    config["info"]["name"] = f"'{new_name}'"
    config["info"]["person_name"] = f"'{person_name}'"
    with open(config_file, "w", encoding="utf-8") as f:
        config.write(f)
    project['name'] = new_name

def save_uploaded_file(project_path, file):
    """保存上传的文件"""
    file_path = Path(project_path) / file.name
    with open(file_path, "wb") as f:
        f.write(file.getbuffer())

def delete_file(project, file_id):
    """删除文件及其配置信息"""
    config_file = Path(project['path']) / "config.conf"
    config = configparser.ConfigParser()
    config.read(config_file, encoding='utf-8')
    
    # 删除物理文件
    file_info = project['files'].get(file_id)
    if file_info:
        file_path = Path(project['path']) / f"{file_id}_{file_info['name']}"
        transcribe_path = Path(project['path']) / f"{file_id}.txt"
        file_path.unlink(missing_ok=True)
        transcribe_path.unlink(missing_ok=True)

        # 从配置文件中删除
        if file_id in config["files"]:
            del config["files"][file_id]
            with open(config_file, "w", encoding='utf-8') as f:
                config.write(f)
            
            # 更新项目信息
            del project['files'][file_id]

def get_project_files(project_path):
    """获取项目文件列表"""
    return [f for f in Path(project_path).glob("*") 
            if f.is_file() and f.name != "config.conf"]
    
    
def upload_project_file(project,file_name,file_data):
    file_id = str(uuid.uuid4())[:8]
    file_path = Path(project['path']) / f"{file_id}_{file_name}"
    with open(file_path, "wb") as f:
        f.write(file_data)
    
    config_file = Path(project['path']) / "config.conf"
    config = configparser.ConfigParser()
    config.read(config_file, encoding='utf-8')

    if "files" not in config:
        config["files"] = {}

    config["files"][file_id] = f"{{'name': '{file_name}', 'status': '1'}}"

    with open(config_file, "w", encoding='utf-8') as f:
        config.write(f)
    