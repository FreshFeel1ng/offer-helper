"""面试助手核心 Agent

直接拼 OpenAI 兼容的 messages 调 LLM（见 llm_client），不依赖 LangChain。
根据问题类型切换回答策略，并在需要时注入简历上下文。
"""

import time
from typing import AsyncGenerator

from . import llm_client
from .classifier import classify_question, get_answer_strategy
from .config import config

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

USER_PROMPT_TEMPLATE = "面试官刚才问了这个问题，请帮我生成一个自然的回答：\n{question}"


def _save_token_usage(prompt_texts: list, completion_text: str, elapsed_ms: float):
    """记录本次调用的 token 用量（估算值）。"""
    try:
        from boss.state import save_token_usage

        prompt_tokens = sum(llm_client.estimate_tokens(t) for t in prompt_texts if t)
        completion_tokens = llm_client.estimate_tokens(completion_text)
        total_tokens = prompt_tokens + completion_tokens
        if total_tokens <= 0:
            print(f"[LLM TOKEN] assistant/{config.llm_model}: 内容为空，跳过统计")
            return
        save_token_usage(
            model=config.llm_model,
            source="interview_assistant",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            elapsed_ms=elapsed_ms,
        )
        print(
            f"[LLM TOKEN] assistant/{config.llm_model}: prompt={prompt_tokens} "
            f"completion={completion_tokens} total={total_tokens} OK"
        )
    except Exception as e:
        print(f"[LLM TOKEN] assistant save failed: {e}")


class InterviewAgent:
    """面试助手 Agent"""

    def __init__(self):
        # 对话历史：[{"role": "user"/"assistant", "content": "..."}]
        self.chat_history: list = []
        # 简历知识库（由 session 注入）
        self.resume_kb = None

    def _build_messages(
        self,
        question: str,
        interview_type: str,
        language: str,
        resume_context: str,
    ) -> list:
        classification = classify_question(question)
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            resumeContext=resume_context or "暂无候选人简历信息，请根据通用知识回答。",
            interviewType=interview_type,
            language=language,
            questionCategory=classification.category.value,
            answerStrategy=get_answer_strategy(classification.category),
        )
        return (
            [{"role": "system", "content": system_prompt}]
            + list(self.chat_history)
            + [{"role": "user", "content": USER_PROMPT_TEMPLATE.format(question=question)}]
        )

    def _resume_context(self, question: str) -> str:
        if self.resume_kb:
            return self.resume_kb.get_context_for_question(question)
        return ""

    async def generate_answer(
        self,
        question: str,
        interview_type: str = "技术面试",
        candidate_background: str = "全栈开发工程师",
        language: str = "zh",
    ) -> str:
        """生成面试回答（一次性返回）"""
        resume_context = self._resume_context(question)
        messages = self._build_messages(question, interview_type, language, resume_context)

        t0 = time.time()
        response = await llm_client.achat(
            messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

        self.chat_history.append({"role": "user", "content": question})
        self.chat_history.append({"role": "assistant", "content": response})
        _save_token_usage([m["content"] for m in messages], response, round((time.time() - t0) * 1000, 0))
        return response

    async def generate_answer_stream(
        self,
        question: str,
        interview_type: str = "技术面试",
        candidate_background: str = "全栈开发工程师",
        language: str = "zh",
    ) -> AsyncGenerator[str, None]:
        """流式生成面试回答"""
        resume_context = self._resume_context(question)
        if resume_context:
            print(f"[Agent] 检索到简历上下文: {len(resume_context)} 字符")
        else:
            print("[Agent] 简历知识库未加载")

        messages = self._build_messages(question, interview_type, language, resume_context)

        t0 = time.time()
        full_response = ""
        async for chunk in llm_client.achat_stream(
            messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        ):
            full_response += chunk
            yield chunk

        elapsed_ms = round((time.time() - t0) * 1000, 0)

        # 保存到历史
        self.chat_history.append({"role": "user", "content": question})
        self.chat_history.append({"role": "assistant", "content": full_response})

        _save_token_usage([m["content"] for m in messages], full_response, elapsed_ms)

    def clear_memory(self):
        self.chat_history.clear()
