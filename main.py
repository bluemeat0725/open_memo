import os
import re
import json
import asyncio
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from pathlib import Path

import httpx
import whisper
from openai import OpenAI,AsyncOpenAI
from pydantic import BaseModel, Field
from tqdm import tqdm

from dotenv import load_dotenv

load_dotenv()


# 配置类
@dataclass
class Config:
    """配置管理"""
    AUDIO_MODEL: str = "whisper"
    API_KEY: str = os.getenv('API_KEY')
    BASE_URL: str = os.getenv('BASE_URL')
    MODEL_NAME: str = os.getenv('MODEL_NAME')
    MAX_TEXT_LENGTH: int = 3000
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 2
    OUTPUT_DIR: str = "output"
    TEMPERATURE: float = 0.2

    @classmethod
    def setup_logging(cls) -> None:
        """设置日志系统"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler('story_processor.log', encoding='utf-8')
            ]
        )


# 数据模型
class StoryInfo(BaseModel):
    """故事信息模型"""
    story_id: int = Field(description="故事序号")
    story_title: str = Field(description="故事名称")
    story_time: str = Field(description="故事发生时间")
    characters: List[str] = Field(description="故事相关人物")
    summary: str = Field(description="故事摘要(200字以内)")


class Story(BaseModel):
    """完整故事模型"""
    info: StoryInfo = Field(description="故事基本信息")
    content: str = Field(description="完整故事内容")


# 核心处理类
class StoryProcessor:
    """故事处理器"""

    def __init__(self, config: Config):
        self.config = config
        self.client = AsyncOpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)
        self.whisper_model = None
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def parse_markdown_json(markdown_text):
        # 匹配包含 JSON 的 Markdown 代码块
        pattern = r'```json\n(.*?)```'
        match = re.search(pattern, markdown_text, re.DOTALL)

        if not match:
            print("Error: 找不到 JSON 代码块")
            return None

        json_str = match.group(1).strip()

        try:
            # 解析 JSON 字符串为 Python 对象
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"JSON 解析失败: {e}")
            return None

    def _parse_json_response(self, response: Any) -> List[Dict[str, Any]]:
        """解析API响应中的JSON内容"""
        try:
            content = response.choices[0].message.content.strip()
            self.logger.debug(f"原始响应: {content}")

            # 直接解析原始响应内容
            data = json.loads(content)

            # 验证结构
            if not isinstance(data, dict):
                raise ValueError("响应不是有效的字典结构")

            stories = data.get("stories", [])
            if not isinstance(stories, list):
                raise ValueError("'stories'字段不是列表类型")

            # 验证每个故事的结构
            required_fields = {"story_id", "story_title", "story_time", "characters", "summary"}
            for idx, story in enumerate(stories):
                if not isinstance(story, dict):
                    raise ValueError(f"故事{idx}不是字典类型")
                missing = required_fields - set(story.keys())
                if missing:
                    raise ValueError(f"故事{idx}缺少字段: {missing}")

            return stories

        except Exception as e:
            self.logger.error(f"解析失败: {str(e)}\n原始内容: {content}")
            raise

    async def process_audio(self, audio_path: str, model='whisper') -> Optional[List[Story]]:
        """处理音频文件"""
        try:
            with tqdm(total=6, desc="处理进度") as progress_bar:
                output_dir = Path(self.config.OUTPUT_DIR)
                output_dir.mkdir(exist_ok=True)
                base_name = Path(audio_path).stem

                if output_dir.joinpath(f"{base_name}_transcript.txt").exists():
                    self.logger.info(f"{base_name}_transcript.txt文件已存在，跳过转录")
                    with open(output_dir.joinpath(f"{base_name}_transcript.txt"), 'r', encoding='utf8') as f:
                        transcript = f.read()
                else:
                    if self.config.AUDIO_MODEL == 'whisper':
                        # 1. 加载模型
                        self.logger.info("正在加载 Whisper 模型...")
                        progress_bar.update(1)
                        # 2. 转录音频
                        self.whisper_model = whisper.load_model("small")
                        transcript = await self.whisper_transcribe_audio(audio_path)
                    elif self.config.AUDIO_MODEL == 'step-asr':
                        transcript = await self.step_transcribe_audio(audio_path)
                        progress_bar.update(1)
                    else:
                        raise ValueError("未知的模型名称")
                    progress_bar.update(1)

                # 3. 分析故事结构
                story_infos = await self._analyze_stories(transcript)
                progress_bar.update(1)

                # 4. 生成故事内容
                stories = await self._generate_stories(story_infos)
                progress_bar.update(1)

                # 5. 保存结果
                await self._save_results(transcript, stories, audio_path)
                progress_bar.update(2)

            return stories

        except Exception as e:
            self.logger.error(f"处理过程出错: {str(e)}", exc_info=True)
            return None

    async def step_transcribe_audio(self, audio_path: str) -> dict:
        try:
            self.logger.info("开始转录音频(阶跃星辰step-asr)...")
            step_key = os.getenv('STEP_KEY')
            url = 'https://api.stepfun.com/v1/audio/transcriptions'
            headers = {
                'Authorization': f'Bearer {step_key}',
            }
            data = {'model': 'step-asr', 'response_format': 'json'}
            async with httpx.AsyncClient(timeout=None) as client:
                with open(audio_path, 'rb') as audio_file:
                    files = {
                        'file': audio_file,
                    }
                    response = await client.post(url, headers=headers, data=data, files=files)
            transcript = response.json()['text']
            # 记录转录结果预览
            preview = transcript[:200] + "..." if len(transcript) > 200 else transcript
            self.logger.info(f"转录完成，预览:\n{preview}")

            return transcript
        except Exception as e:
            self.logger.error(f"音频转录失败: {str(e)}")
            raise

    async def whisper_transcribe_audio(self, audio_path: str, model_name=None) -> str:
        """音频转录"""
        try:
            self.logger.info("开始转录音频...")
            result = self.whisper_model.transcribe(audio_path, fp16=False)
            transcript = result['text']

            # 记录转录结果预览
            preview = transcript[:200] + "..." if len(transcript) > 200 else transcript
            self.logger.info(f"转录完成，预览:\n{preview}")

            return transcript
        except Exception as e:
            self.logger.error(f"音频转录失败: {str(e)}")
            raise

    async def _analyze_stories(self, text: str) -> List[Dict[str, Any]]:
        """分析故事结构"""
        self.logger.info("正在分析故事结构...")
        system_prompt = self._get_analysis_prompt()

        for attempt in range(self.config.MAX_RETRIES):
            try:
                response = await self._make_api_call(
                    model=self.config.MODEL_NAME,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"请分析这段内容：{text[:self.config.MAX_TEXT_LENGTH]}"}
                    ],
                    temperature=0.1
                )

                # 在解析响应之前，打印原始响应以进行调试
                print("模型返回的原始响应:")
                print(response.choices[0].message.content)

                # stories = self._parse_json_response(response)
                stories = self.parse_markdown_json(response.choices[0].message.content)
                stories = stories.get('stories', [])

                self.logger.info(f"成功识别出 {len(stories)} 个故事")
                return stories

            except Exception as e:
                self.logger.warning(f"分析尝试 {attempt + 1}/{self.config.MAX_RETRIES} 失败: {str(e)}")
                if attempt == self.config.MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(self.config.RETRY_DELAY)

    async def _generate_stories(self, story_infos: List[Dict[str, Any]]) -> List[Story]:
        """并行生成故事内容"""
        self.logger.info(f"开始并行生成 {len(story_infos)} 个故事...")
        tasks = [self._generate_single_story(info) for info in story_infos]
        # tasks = [self._generate_single_story(story_infos)]

        stories = []
        for task in asyncio.as_completed(tasks):
            try:
                story = await task
                if story:
                    stories.append(story)
                    self.logger.info(f"故事 {story.info.story_id} 生成完成")
            except Exception as e:
                self.logger.error(f"故事生成错误: {str(e)}")

        return sorted(stories, key=lambda x: x.info.story_id)

    async def _generate_single_story(self, story_info: Dict[str, Any]) -> Optional[Story]:
        """生成单个故事"""
        prompt = self._get_story_prompt(story_info)

        for attempt in range(self.config.MAX_RETRIES):
            try:
                response = await self._make_api_call(
                    model=self.config.MODEL_NAME,
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": "你是一个专业的故事创作者，请直接输出故事内容。"}
                    ],
                    temperature=self.config.TEMPERATURE
                )
                return Story(
                    info=StoryInfo(**story_info),
                    content=response.choices[0].message.content.strip()
                )
            except Exception as e:
                if attempt == self.config.MAX_RETRIES - 1:
                    self.logger.error(f"生成故事 {story_info['story_id']} 失败: {str(e)}")
                    return None
                await asyncio.sleep(self.config.RETRY_DELAY)

    async def _make_api_call(self, **kwargs) -> Any:
        try:
            # 添加响应格式参数
            # kwargs.setdefault('response_format', {'type': 'json_object'})
            response = await self.client.chat.completions.create(**kwargs)
            return response
        except Exception as e:
            self.logger.error(f"API调用失败: {str(e)}")
            raise

    async def _save_results(self, transcript: str, stories: List[Story], audio_path: str) -> None:
        """保存处理结果"""
        self.logger.info("正在保存结果...")
        output_dir = Path(self.config.OUTPUT_DIR)
        output_dir.mkdir(exist_ok=True)

        base_name = Path(audio_path).stem

        # 保存转录文本
        (output_dir / f"{base_name}_transcript.txt").write_text(transcript, encoding='utf-8')

        # 保存故事内容
        self._save_stories_text(output_dir / f"{base_name}_stories.txt", stories)

        # 保存 JSON
        self._save_stories_json(output_dir / f"{base_name}_stories.json", stories)

    @staticmethod
    def _get_analysis_prompt() -> str:
        """获取分析提示词"""
        return """
        # 角色
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

    @staticmethod
    def _get_story_prompt(story_info: Dict[str, Any]) -> str:
        """获取故事生成提示词"""
        return f"""请基于以下信息，编写一个完整的故事。请直接输出故事内容，不要包含任何格式标记：

        标题：{story_info['story_title']}
        时间：{story_info['story_time']}
        人物：{', '.join(story_info['characters'])}
        梗概：{story_info['summary']}

        要求：
        1. 保持故事的完整性和连贯性
        2. 添加适当的环境描写和细节
        3. 展现人物的性格特征和情感变化
        4. 故事长度控制在1000字左右
        5. 运用报告文学的语言风格"""

    def _save_stories_text(self, path: Path, stories: List[Story]) -> None:
        """保存故事文本"""
        with path.open('w', encoding='utf-8') as f:
            for story in stories:
                f.write(f"故事序号: {story.info.story_id}\n")
                f.write(f"故事标题: {story.info.story_title}\n")
                f.write(f"发生时间: {story.info.story_time}\n")
                f.write(f"相关人物: {', '.join(story.info.characters)}\n")
                f.write(f"故事摘要: {story.info.summary}\n")
                f.write("\n完整故事内容:\n")
                f.write(story.content)
                f.write("\n\n" + "=" * 50 + "\n\n")

    def _save_stories_json(self, path: Path, stories: List[Story]) -> None:
        """保存故事JSON"""
        with path.open('w', encoding='utf-8') as f:
            json.dump([story.model_dump() for story in stories], f, ensure_ascii=False, indent=2)


async def main(audio_path, config):
    # 初始化配置和日志

    config.setup_logging()

    # 设置音频文件路径

    if not os.path.exists(audio_path):
        logging.error(f"错误：找不到音频文件 {audio_path}")
        return

    # 创建处理器并处理音频
    processor = StoryProcessor(config)
    stories = await processor.process_audio(audio_path)

    if stories:
        logging.info("\n=== 处理完成的故事 ===")
        for story in stories:
            logging.info(f"\n故事 {story.info.story_id}: {story.info.story_title}")
            logging.info(f"发生时间: {story.info.story_time}")
            logging.info(f"相关人物: {', '.join(story.info.characters)}")
            logging.info(f"摘要: {story.info.summary}")
    else:
        logging.error("故事生成失败")


if __name__ == "__main__":
    # audio_path = "./audio_dir/白石老人自述.mp3"
    audio_path = "./audio_dir/吴孟达-最中意武状元苏乞儿youtube_szboYXG9W0Q.mp3"
    config = Config(AUDIO_MODEL='step-asr')
    asyncio.run(main(audio_path, config))
