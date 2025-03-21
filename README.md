# open_memo

## 项目介绍
记录口述人生故事   
帮助AI学习者了解有关语音识别，prompt工程，AI接口调用，结构化输出等常见AI技术概念与技术实现细节   
主要流程： 语音转写 -> 分析故事结构 -> 生成故事内容   


## 环境安装

1. 安装python环境
2. 创建虚拟环境
    - 进入项目文件夹
    - 执行：`python -m venv venv`
        - 激活虚拟环境：
            - win: `.\env\Scripts\activate`
            - mac: `source env/bin/activate`
3. 安装依赖库 `pip install -r requirements.txt`
4. 环境变量.env文件配置
   项目会使用到各类AI服务商接口，各服务对应的key可配置在环境变量.env文件中   
   .env文件内容参考 .env.temp 文件， 填入所需变量后复制文件并重命名为.env

## 项目使用

### 1. 项目配置

环境变量配置，环境变量可配置到.env文件中

```.env
#智谱baseurl, glm-4-plus,glm-4-air
BASE_URL=https://open.bigmodel.cn/api/paas/v4/
#DeepSeek,baseurl, deepseek-chat,deepseek-reasoner
#BASE_URL=https://api.deepseek.com

API_KEY=
MODEL_NAME=glm-4-plus
```

#### 模型服务

支持适配openai接口格式的模型服务商，不同服务商需配置相应的BASE_URL，API_KEY以及MODEL_NAME
例-智谱：
BASE_URL=https://open.bigmodel.cn/api/paas/v4/   
MODEL_NAME=glm-4-plus

例-DeepSeek：
BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-chat

#### 语音转写服务

语音转写默认使用本地运行openai-whisper服务  
支持配置stepfun语音转写服务,需配置环境变量:

```.env
AUDIO_MODEL=step-asr   
STEP_KEY=
```

stepfun Doc: https://platform.stepfun.com/docs/api-reference/audio/transcriptions

### 2. 启动服务

服务运行

1. 配置要转写的语音文件audio_path
打开main.py 在文件末尾配置音频文件路径变量audio_path
```main.py
if __name__ == "__main__":
    # 配置要转写的语音文件audio_path，默认音频文件位置为当前目录下的audio_dir文件夹
    audio_path = "./audio_dir/白石老人自述.mp3"
    config = Config(AUDIO_MODEL='step-asr')
    asyncio.run(main(audio_path, config))
```
2. 运行main.py脚本：`python main.py`
3. 查看结果

### 3. 技术细节见notebook
完成环境安装后，命令行运行： `jupyter lab --notebook-dir=.` 启动笔记   
在跳出的浏览页面中打开 note/open_memo.ipynb 查看运行样例，解释并尝试自己运行代码，实验不同prompt对模型输出的影响

### 4. 添加Streamlit应用
项目位置 ./app

[Streamlit应用说明](./app/readme.md)

![openmemo.gif](openmemo.gif)
