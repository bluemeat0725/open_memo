from openai import OpenAI
from dataclasses import dataclass
import os
import requests
import re
import json
from pathlib import Path
import streamlit as st

from utils import load_project
import threading

# 不再需要 load_dotenv()

PROJECT_ROOT = Path("project_dir")
if not PROJECT_ROOT.exists():
    PROJECT_ROOT.mkdir(exist_ok=True)

@dataclass
class Config:
    """配置管理"""
    API_KEY: str = st.secrets.get("API_KEY", "")
    BASE_URL: str = st.secrets.get("BASE_URL", "")
    MODEL_NAME: str = st.secrets.get("MODEL_NAME", "")
config= Config()

client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)

# 在文件顶部添加全局锁
transcribe_lock = threading.Lock()

def file_transcribe(project_id, file_id):
    """文件转录"""
    # 使用锁确保同一时间只有一个转录任务
    with transcribe_lock:
        api_result=None
        try:
            project = load_project(project_id)
            
            if project:
                transcribe_path = Path(project['path']) / f"{file_id}.txt"
                transcribe_path.unlink(missing_ok=True)
                file = project.get('files',{})[file_id]
                audio_path = Path(project['path']) / f"{file_id}_{file['name']}"
                
                step_key = st.secrets.get("STEP_KEY", "")
                url = 'https://api.stepfun.com/v1/audio/transcriptions'
                headers = {
                    'Authorization': f'Bearer {step_key}',
                }
                
                # 读取文件内容而不是使用文件对象
                audio_file_data = open(audio_path, 'rb').read()
                files = {
                    'file': ('audio.mp3', audio_file_data, 'audio/mpeg')
                }
                
                data={'model': 'step-asr', 'response_format': 'json'}
                response = requests.post(url, headers=headers, files=files, data=data)
                api_result = response.json()
                transcribe = api_result['text']
                
                
                with open(transcribe_path, 'w', encoding='utf-8') as f:
                    f.write(transcribe)
                return transcribe
        except Exception as e:
            print(f"转录错误: {e} ")
            print(api_result)
            return None

# thread run file_transcribe
# 添加一个全局字典来跟踪正在处理的文件
active_transcriptions = {}

def thread_file_transcribe(project_id, file_id):
    """文件转录"""
    # 检查该文件是否正在处理中
    file_key = f"{project_id}_{file_id}"
    if file_key in active_transcriptions:
        return None
        
    try:
        active_transcriptions[file_key] = True
        
        # 创建一个函数来执行转录并打印结果
        def transcribe_and_print():
            result = file_transcribe(project_id, file_id)
            result_info = result or "fail"
            result_info = result_info[:10]+'...'
            print(f"转录完成 - 项目: {project_id}, 文件: {file_id}, 结果: {result_info}...'")
            return result
            
        thread = threading.Thread(target=transcribe_and_print)
        thread.start()
        return thread
    finally:
        # 确保处理完后移除状态
        if file_key in active_transcriptions:
            del active_transcriptions[file_key]

def parse_markdown_json(markdown_text):
    # 匹配包含 JSON 的 Markdown 代码块
    pattern = r'```json\n(.*?)```'
    match = re.search(pattern, markdown_text, re.DOTALL)

    if not match:
        print("Error: 找不到 JSON 代码块")
        return {}

    json_str = match.group(1).strip()

    try:
        # 解析 JSON 字符串为 Python 对象
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
        return {}

analysis_prompt="""# 角色
你是一名专业文学分析师，擅长多故事解构和关键信息提炼。具备精准识别叙事单元、解析时空逻辑、提取核心要素的能力。

## 任务说明
### 核心功能：
对输入的复合文本进行深度解析，完成：
1. 独立叙事单元的识别与分割
2. 故事要素的精准提取
3. 结构化数据输出

## 技能树
### 技能 1：故事拆分
1. 逐句分析文本，识别时间/地点/人物的非连续突变
2. 通过叙事断层检测判断独立故事数量
3. 确定每个故事的起止边界（承转合节点）

### 技能 2：结构化输出
1. 为每个故事创建独立数据对象
2. 要素提取标准：
    - 标题：基于核心矛盾提炼（中性表述）
    - 时间：精确到最小可识别单位（例："工业革命初期"→"1760年代"）
    - 人物：排除次要人物（出场＜3次/无关键行动）
    - 摘要：包含「冲突起源-关键转折-结局」三要素

### 技能 3：格式规范
1. 严格遵循以下的JSON架构，不要添加任何其他额外内容：
{
    "stories": [
        {
            "story_id": 1,
            "story_title": "标题",
            "story_time": "时间描述",
            "characters": ["人物1", "人物2"],
            "summary": "摘要内容"
        }
    ]
}
2. 摘要长度控制：
    - 中文不超过200字（含标点）
    - 英文不超过400字符

## 约束条件
1. 必须直接输出合法JSON，不要添加任何额外说明
2. 绝对禁止合并具有时空断层的故事
3. 时间解析必须满足：
    - 明确时间＞模糊时间（原文"春天"需保持模糊）
    - 拒绝推断不存在的时间信息
4. 人物字段需去重处理


## 错误处理
1. 当检测到非故事内容（论述/说明/对话）时：
    - 丢弃非叙事段落
    - 返回错误类型："NON_STORY_CONTENT"
2. 当出现无法解析的时间信息时：
    - 保留原文表述
    - 添加注释："TIME_AMBIGUITY"     
"""

def load_story_prompt(story_info: dict) -> list:
    """获取故事生成提示词"""
    prompts = []
    stories=story_info.get('stories',[])
    for story in stories:
        story_content=f"""
标题：{story['story_title']}
时间：{story['story_time']}
人物：{', '.join(story['characters'])}
梗概：{story['summary']}"""
    
    
        prompt =  f"""请基于以下信息，编写一个完整的故事。请直接输出故事内容，不要包含任何格式标记：
        
        {story_content}
        
        要求：
        1. 保持故事的完整性和连贯性
        2. 添加适当的环境描写和细节
        3. 展现人物的性格特征和情感变化
        4. 故事长度控制在1000字左右
        5. 运用报告文学的语言风格
        """
        prompts.append([story_content,prompt])
    return prompts

def memo_analysis(project_id, transcribe_text):
    try:
        PROJECT_ROOT = Path("project_dir")
        project_path = PROJECT_ROOT / project_id
        memo_file = Path(project_path) / "memo.txt"
        memo_file.unlink(missing_ok=True)
        project = load_project(project_id) or {}
        person_name = project.get("person_name","")
        
        transcribe_text = f'{f"讲述人："+person_name}\n{transcribe_text}' if person_name else transcribe_text
        
        analysis_response = client.chat.completions.create(
                        model=config.MODEL_NAME,
                        messages=[
                            {"role": "system", "content": analysis_prompt},
                            {"role": "user", "content": f"请分析这些内容片段：{transcribe_text}"}
                        ],
                        temperature=0.3
                    )
        story_data=parse_markdown_json(analysis_response.choices[0].message.content)
        story_prompts=load_story_prompt(story_data)
        print('story_data:',story_data)
        memo=''
        for story_content,prompt in story_prompts:
            # memo_response = client.chat.completions.create(
            #                 model=config.MODEL_NAME,
            #                 messages=[
            #                     {"role": "system", "content": prompt},
            #                     {"role": "user", "content": "你是一个专业的故事创作者，请直接输出故事内容。"}
            #                 ],
            #                 temperature=0.3
            #             )
            # memo_clip = memo_response.choices[0].message.content or ''
            
            memo_clip=''
            memo_response = client.chat.completions.create(
                model=config.MODEL_NAME,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "你是一个专业的故事创作者，请直接输出故事内容。"}
                ],
                temperature=0.3,
                stream=True
            )
            for stream in memo_response:
                content = stream.choices[0].delta.content or ""
                memo_clip += content
                print(content, end="", flush=True)  
            story_content = story_content.replace('\n', '\n\n')
            if memo:
                memo+= '---\n\n'
                memo +=  f'{story_content}\n故事内容:\n\n{memo_clip}\n\n'
            else:
                memo = f'{story_content}\n故事内容:\n\n{memo_clip}\n\n'

        memo=memo.strip()
        with open(memo_file, 'w', encoding='utf-8') as f:
                f.write(memo)
        
    except Exception as e:
        return str(e)
  
def thread_file_memo_analysis(project_id, transcribe_text):
    """文件转录"""
    # 创建新线程执行转录任务
    thread = threading.Thread(target=memo_analysis, args=(project_id, transcribe_text))
    thread.start()
    return thread  




if __name__ == "__main__":
    print(config)
    
    file_transcribe('0f453e25','dce86e01')
