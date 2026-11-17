"""
面试辅助模块 - 实时面试回答生成

提供:
- 面试问题实时回答生成 (Agent)
- 问题分类 (Classifier)
- 语音文本预处理 (Speech)
- 简历解析与检索 (Resume：关键词 / 语义向量)
- 系统音频捕获 (AudioCapture，可选)
- 模拟面试 (Mock)

LLM 调用直接走 OpenAI 兼容协议（llm_client），不依赖 Agent 框架或向量数据库。
"""
