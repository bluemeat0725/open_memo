import streamlit as st
import os
import uuid
import shutil
import configparser
from pathlib import Path
import time
import ast

from utils import update_project_name, load_project, delete_file, load_projects, create_project, upload_project_file
from ai_utils import thread_file_transcribe,thread_file_memo_analysis

# 项目根目录
PROJECT_ROOT = Path("project_dir")
if not PROJECT_ROOT.exists():
    PROJECT_ROOT.mkdir(exist_ok=True)
if "file_uploader_key" not in st.session_state:
    st.session_state["file_uploader_key"] = 0


def project_page(project):
    st.header(f"Open MEMO")

    with st.form("项目名称", clear_on_submit=False):
        col1, col2, col3 = st.columns([5, 1, 1])
        with col1:
            new_name = st.text_input(
                "项目名称", project['name'], label_visibility="collapsed")
        with col2:
            save_name = st.form_submit_button("修改名称", use_container_width=True)
        with col3:
            delete_project = st.form_submit_button("删除项目", use_container_width=True)
        if save_name and new_name != project['name']:
            update_project_name(project, new_name)
            st.session_state.current_project = project
            st.session_state.projects = load_projects()
            st.rerun()
        if delete_project:
            if "confirm_delete" not in st.session_state:
                st.session_state.confirm_delete = True
                st.rerun()
    
    # 显示确认对话框
    if "confirm_delete" in st.session_state and st.session_state.confirm_delete:
        with st.form("确认删除", clear_on_submit=True):
            st.warning(f"确定要删除项目 '{project['name']}' 吗？此操作不可恢复！")
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("确认删除", use_container_width=True):
                    # 删除项目文件夹
                    shutil.rmtree(Path(project['path']))
                    # 清除会话状态
                    del st.session_state.current_project
                    del st.session_state.confirm_delete
                    # 重新加载项目列表
                    st.session_state.projects = load_projects()
                    st.success("项目已删除")
                    st.rerun()
            with col2:
                if st.form_submit_button("取消", use_container_width=True):
                    del st.session_state.confirm_delete
                    st.rerun()

    # 文件上传
    uploaded_file = st.file_uploader(
        "上传文件", accept_multiple_files=False, key=st.session_state['file_uploader_key'])
    if uploaded_file:
        file_name = uploaded_file.name
        file_data = uploaded_file.getbuffer()
        upload_project_file(project, file_name, file_data)

        # 创建临时消息
        message = st.empty()
        message.success("文件上传成功！")
        time.sleep(3)
        message.empty()
        st.session_state["file_uploader_key"] += 1
        st.session_state.current_project = load_project(project['id'])
        st.rerun()

    pagebt1, pagebt2, _ = st.columns([1, 1, 20])
    with pagebt1:

        proj_refresh = st.button("刷新")
        if proj_refresh:
            st.session_state.current_project = load_project(project['id'])
            st.rerun()
    with pagebt2: 
        proj_reset = st.button("重置")
        if proj_reset:
            config_file = Path(project['path']) / "config.conf"
            config = configparser.ConfigParser()
            config.read(config_file, encoding='utf-8')
            config['info']['memo_stat']='0'
            for file_id, file_info_str in config["files"].items():
                file_info = ast.literal_eval(file_info_str)
                file_info['status'] = '1'
                config["files"][file_id] = str(file_info)
            with open(config_file, "w", encoding='utf-8') as f:
                config.write(f)
            st.session_state.current_project = load_project(project['id'])
            st.rerun()    

    # 显示已上传的文件
    project_transcribe=''
    project_transcribe_text=''
    
    with st.expander("文件列表"):
        if project['files']:
            for ind, pfile in enumerate(project['files'].items(),start=1):
                file_id, file_info = pfile
                filename, transcribe_btn, delete_btn = st.columns([12, 1, 0.8])
                project_transcribe+=f"#### {file_info['name']}\n{file_info['transcribe']}\n\n"
                project_transcribe_text+=f"clip{ind}\n{file_info['transcribe']}\n\n"
                with filename:
                    st.write(f"📄 {file_info['name']}")
                with transcribe_btn:
                    if file_info['status'] == '1':  # 状态为1时可以转录
                        if file_info['transcribe']:
                            trans_btn_str = '重新转录'
                        else:
                            trans_btn_str = '转录'
                            
                        if st.button(trans_btn_str, key=f"edit_{file_id}"):      
                            # 启动转录线程
                            thread_file_transcribe(project['id'], file_id)  
                            # 刷新页面
                            time.sleep(1)
                            config_file = Path(project['path']) / "config.conf"
                            config = configparser.ConfigParser()
                            config.read(config_file, encoding='utf-8')
                            
                            # 更新状态
                            file_data = ast.literal_eval(config["files"][file_id])
                            file_data['status'] = '0'
                            config["files"][file_id] = str(file_data)
                            # 保存配置
                            with open(config_file, "w", encoding='utf-8') as f:
                                config.write(f)
                            st.session_state.current_project = load_project(project['id'])
                            st.rerun()
                    else:  # 状态为0时显示运行中
                        st.button("运行中", key=f"edit_{file_id}", disabled=True)
                with delete_btn:
                    if st.button("删除", key=f"del_{file_id}"):
                        delete_file(project, file_id)
                        st.success(f"文件 {file_info['name']} 已删除")
                        st.rerun()
    with st.expander('转录内容'):
        st.markdown(project_transcribe)
    
    st.subheader('Memo')
    if project['memo_stat']=='1':
        gen_memo_btn=st.button("生成中", disabled=True)
    else:
        gen_memo_btn = st.button('生成')
    memo_file = Path(project['path']) / "memo.txt"

    if gen_memo_btn:
        if len(project_transcribe_text)<100:
            st.warning('转录内容太少，请搜集更多故事')
        else:
            thread_file_memo_analysis(project['id'], project_transcribe_text)
            time.sleep(1)
            config_file = Path(project['path']) / "config.conf"
            config = configparser.ConfigParser()
            config.read(config_file, encoding='utf-8')
            config['info']['memo_stat']='1'
            with open(config_file, "w", encoding='utf-8') as f:
                config.write(f)
        st.session_state.current_project = load_project(project['id'])
        st.rerun()
    if os.path.exists(memo_file):
        with open(memo_file, 'r', encoding='utf-8') as f:
            memo = f.read()
        st.markdown(memo)
    
            


def main():
    st.set_page_config(
        page_title="Open Memo",
        page_icon="📝",
        layout="wide"
    )

    # 加载项目列表
    if "projects" not in st.session_state:
        st.session_state.projects = load_projects()

    # 侧边栏
    with st.sidebar:
        # 项目列表
        st.header("Memo项目")
        for project in st.session_state.projects:
            if st.button(f"📁 {project['name']}", key=f"nav_{project['id']}"):
                st.session_state.current_project = load_project(project['id'])
                st.rerun()
                
        # 分隔线
        st.markdown("---")

        # 创建新项目
        st.subheader("创建新项目")
        with st.form("create_project", clear_on_submit=True):
            project_name = st.text_input("项目名称")
            person_name = st.text_input("讲述人")
            submit = st.form_submit_button("创建项目")

            if submit and project_name:
                project = create_project(project_name,person_name)
                project = load_project(project['id'])
                st.session_state.projects.append(project)
                st.session_state.current_project = project
                st.success(f"项目 '{project_name}' 创建成功！")
                st.rerun()

    # 主要内容区域
    if "current_project" in st.session_state:

        project_info = st.session_state.current_project.copy()
        # print project info exclude transcribe
        project_info['memo'] = project_info['memo'][:10]+'...'
        project_info['files'] = {i:v['name'] for i,v in project_info['files'].items()}
        print(project_info)
        project_page(st.session_state.current_project)
    else:
        st.title("Open Memo")
        st.write("👈 选择或创建项目")


if __name__ == "__main__":
    main()
