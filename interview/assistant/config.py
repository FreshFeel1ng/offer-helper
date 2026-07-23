"""
面试助手配置 - 兼容 offer-helper 的 LLM 配置体系

优先从 boss_state (PostgreSQL settings表) 读取配置,
回退到环境变量。
"""
import os
import sys
from pathlib import Path

# 确保能导入父项目模块
_PARENT = Path(__file__).parent.parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))


class AssistantConfig:
    """面试辅助配置"""

    def __init__(self):
        # LLM 配置（优先从 boss_state 读取，回退环境变量）
        self.deepseek_api_key: str = ""
        self.deepseek_base_url: str = "https://api.deepseek.com/v1"
        self.llm_model: str = "deepseek-chat"
        self.server_port: int = 3001
        self.temperature: float = 0.7
        self.max_tokens: int = 500

        # MinerU PDF 解析
        self.mineru_api_token: str = os.getenv("MINERU_API_TOKEN", "")

        # 硅基流动（嵌入模型）
        self.siliconflow_api_key: str = os.getenv("SILICONFLOW_API_KEY", "")
        self.siliconflow_base_url: str = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")

        # Milvus
        self.milvus_host: str = os.getenv("MILVUS_HOST", "localhost")
        self.milvus_port: int = int(os.getenv("MILVUS_PORT", "19530"))
        self.embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")

        # 从 offer-helper 的 boss_state 加载 AI 配置
        self._load_from_boss_state()

    def _load_from_boss_state(self):
        """从 boss_state SQLite 读取配置"""
        try:
            from boss.state import get_setting, get_db
            get_db()

            key = get_setting("ai_api_key")
            if key:
                self.deepseek_api_key = key

            url = get_setting("ai_base_url")
            if url:
                self.deepseek_base_url = url

            model = get_setting("ai_model")
            if model:
                self.llm_model = model

            # MinerU token
            mineru_token = get_setting("mineru_api_token")
            if mineru_token:
                self.mineru_api_token = mineru_token
                os.environ["MINERU_API_TOKEN"] = mineru_token

            # 硅基流动 (BGE-M3 embedding)
            sf_key = get_setting("siliconflow_api_key")
            if sf_key:
                self.siliconflow_api_key = sf_key
                os.environ["SILICONFLOW_API_KEY"] = sf_key

            # 嵌入模型
            emb_model = get_setting("embedding_model")
            if emb_model:
                self.embedding_model = emb_model

            print(f"[AssistantConfig] 从 boss_state 加载配置: model={self.llm_model}, embed={self.embedding_model}")
        except Exception as e:
            print(f"[AssistantConfig] boss_state 加载失败，使用环境变量: {e}")
            # 回退环境变量
            env_key = os.getenv("DEEPSEEK_API_KEY", "")
            if env_key:
                self.deepseek_api_key = env_key

    def validate(self):
        """验证必要配置"""
        if not self.deepseek_api_key:
            print("[WARN] AI API Key 未配置，请在设置页配置或设置 DEEPSEEK_API_KEY 环境变量")


# 全局配置实例
config = AssistantConfig()
