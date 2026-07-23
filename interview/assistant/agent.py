"""
面试助手核心 Agent

基于 LangChain + LLM，生成既专业又口语化的面试回答。
兼容 offer-helper 的 LLM 配置体系。
"""
import time
from typing import AsyncGenerator, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.callbacks import BaseCallbackHandler

from .config import config
from .classifier import classify_question, get_answer_strategy


class _TokenLogger(BaseCallbackHandler):
    """LangChain 回调：记录 LLM 每次调用的 token 用量"""

    def __init__(self):
        self._t0 = None

    def on_llm_start(self, serialized, prompts, **kwargs):
        self._t0 = time.time()

    def on_llm_end(self, response, **kwargs):
        elapsed = time.time() - (self._t0 or time.time())
        usage = {}
        if hasattr(response, 'llm_output') and response.llm_output:
            usage = response.llm_output.get('token_usage', {})
        if not usage and hasattr(response, 'response_metadata'):
            usage = response.response_metadata.get('token_usage', {})
        if not usage and hasattr(response, 'generations') and response.generations:
            gen = response.generations[0][0]
            if hasattr(gen, 'generation_info'):
                usage = gen.generation_info or {}

        prompt_tok = usage.get('prompt_tokens', 0) or 0
        completion_tok = usage.get('completion_tokens', 0) or 0
        total_tok = usage.get('total_tokens', 0) or (prompt_tok + completion_tok)

        if total_tok > 0:
            try:
                from boss.state import save_token_usage
                save_token_usage(
                    model=config.llm_model,
                    source="interview_assistant",
                    prompt_tokens=prompt_tok,
                    completion_tokens=completion_tok,
                    total_tokens=total_tok,
                    elapsed_ms=round(elapsed * 1000, 0),
                )
                print(f"[LLM TOKEN] assistant/{config.llm_model}: {total_tok}t OK")
            except Exception as e:
                print(f"[LLM TOKEN] assistant save failed: {e}")
        else:
            print(f"[LLM TOKEN] assistant/{config.llm_model}: 未获取到 token 用量 (usage={usage})")

        self._t0 = None

SYSTEM_PROMPT_TEMPLATE = """你是一个面试辅助 AI，帮助在面试中的候选人现场生成回答。

## 回答策略：根据问题类型区分处理

### A) 当问题是纯知识/概念题（如"HashMap是什么"、"Spring自动装配原理"）：
- **不需要提项目经历**，直接专业、详细地解释概念
- 回答要准确、有深度，展现扎实的技术功底
- 先说核心定义，再展开关键细节，最后可提一两个最佳实践
- 口语化但内容专业，100-250字

### B) 当问题是经历/项目题（如"介绍你的项目"、"你做过什么"）：
- **必须引用下方简历**中的具体项目名、技术栈、公司名
- 严格使用简历中的真实经历，禁止编造

## 候选人简历（仅B类问题需要参考）
{resumeContext}

## 回答风格
- 口语化，像真人说话（嗯、我觉得、其实吧）
- 第一人称"我"
- 面试类型：{interviewType}，语言：{language}

## 问题信息
- 类别：{questionCategory}
- 策略：{answerStrategy}"""


class InterviewAgent:
    """面试助手 Agent"""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=config.llm_model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
        )
        # 用简单的列表存储对话历史
        self.chat_history: list = []
        # 简历知识库（由 session 注入）
        self.resume_kb = None

        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT_TEMPLATE),
            MessagesPlaceholder("chat_history"),
            ("human", "面试官刚才问了这个问题，请帮我生成一个自然的回答：\n{question}"),
        ])

        self.chain = prompt | self.llm | StrOutputParser()

    async def generate_answer(
        self,
        question: str,
        interview_type: str = "技术面试",
        candidate_background: str = "全栈开发工程师",
        language: str = "zh",
    ) -> str:
        """生成面试回答"""
        classification = classify_question(question)

        # 检索简历相关上下文
        resume_context = ""
        if self.resume_kb:
            resume_context = self.resume_kb.get_context_for_question(question)

        response = await self.chain.ainvoke({
            "question": question,
            "chat_history": self.chat_history,
            "interviewType": interview_type,
            "candidateBackground": candidate_background,
            "language": language,
            "questionCategory": classification.category.value,
            "answerStrategy": get_answer_strategy(classification.category),
            "resumeContext": resume_context if resume_context else "暂无候选人简历信息，请根据通用知识回答。",
        })

        # 保存到历史
        self.chat_history.append(HumanMessage(content=question))
        self.chat_history.append(AIMessage(content=response))

        return response

    async def generate_answer_stream(
        self,
        question: str,
        interview_type: str = "技术面试",
        candidate_background: str = "全栈开发工程师",
        language: str = "zh",
    ) -> AsyncGenerator[str, None]:
        """流式生成面试回答"""
        token_logger = _TokenLogger()
        streaming_llm = ChatOpenAI(
            model=config.llm_model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            api_key=config.deepseek_api_key,
            base_url=config.deepseek_base_url,
            streaming=True,
            callbacks=[token_logger],
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT_TEMPLATE),
            MessagesPlaceholder("chat_history"),
            ("human", "面试官刚才问了这个问题，请帮我生成一个自然的回答：\n{question}"),
        ])

        chain = prompt | streaming_llm | StrOutputParser()

        classification = classify_question(question)

        # 检索简历相关上下文
        resume_context = ""
        if self.resume_kb and self.resume_kb.resume:
            resume_context = self.resume_kb.get_context_for_question(question)
            print(f"[Agent] 检索到简历上下文: {len(resume_context)} 字符")
        else:
            print(f"[Agent] 简历知识库未加载")

        full_response = ""
        async for chunk in chain.astream({
            "question": question,
            "chat_history": self.chat_history,
            "interviewType": interview_type,
            "candidateBackground": candidate_background,
            "language": language,
            "questionCategory": classification.category.value,
            "answerStrategy": get_answer_strategy(classification.category),
            "resumeContext": resume_context if resume_context else "暂无候选人简历信息，请根据通用知识回答。",
        }):
            full_response += chunk
            yield chunk

        # 保存到历史
        self.chat_history.append(HumanMessage(content=question))
        self.chat_history.append(AIMessage(content=full_response))

    def clear_memory(self):
        self.chat_history.clear()
