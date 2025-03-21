# Streamlit app
独立 Streamlit app 界面，用于音频转录和故事生成。

## 功能特点
- 支持音频文件上传和管理
- 自动音频转录
- 智能故事分析和生成
- 多项目管理

## 项目启动
1. 进入文件夹
```bash
cd app
```

2. 创建虚拟环境
`python -m venv venv`

3. 激活虚拟环境
- windows
`.\venv\Scripts\activate`

4. 安装依赖
`pip install -r requirements.txt`

5. 配置环境变量
在项目根目录创建 .streamlit 文件夹，并创建 secrets.toml 文件：
```toml
API_KEY = "你的OpenAI API密钥"
BASE_URL = "OpenAI API基础URL"
MODEL_NAME = "gpt-3.5-turbo"
STEP_KEY = "Step ASR API密钥"
```
OpenAI Compatible API（符合openai接口规范） 密钥和基础URL 可在各个模型服务平台获取。

6. 启动应用
`streamlit run app.py`
