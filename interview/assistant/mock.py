"""
模拟面试模块
- 使用 DeepSeek 根据职位/话题自动出题
- 语音输入回答，AI 逐轮评分
- 面试结束后生成综合评分报告
"""

import json
import time
from typing import AsyncGenerator, Optional
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from .config import config as assistant_config


# ── Question generation prompt ──
QUESTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位专业的{position}面试官，正在进行一场{difficulty}难度的模拟面试。

当前是第 {round_num} / {max_rounds} 轮。
面试主题/岗位：{position}
面试重点方向：{topic}

已问过的问题和回答：
{history}

请根据以上信息，生成下一道面试问题。要求：
1. 问题要覆盖不同的考察维度（技术基础、项目经验、系统设计、行为面试等）
2. 如果前面问过某个方向，下一题换另一个方向
3. 难度逐步递增
4. 问题要具体，有场景感，不能太宽泛
5. 如果是最后一轮，可以问一个综合性或总结性问题
6. 只输出问题本身，不要加任何前缀说明"""),
    ("human", "请出下一道面试题"),
])

# ── Evaluation prompt ──
EVALUATION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位资深的{position}面试官。请对候选人在一道面试题上的回答进行评分和点评。

**面试题**：{question}
**候选人回答**：{answer}
**面试难度**：{difficulty}

请从以下维度评估并输出 JSON（不要输出其他内容）：
{{
  "score": 0-10 的整数评分,
  "correctness": "回答的准确性和专业性",
  "depth": "回答的深度和细节",
  "communication": "表达清晰度和逻辑性",
  "comment": "简短的点评（1-2句）"
}}

评分标准：
- 8-10: 回答准确，有深度，表达清晰，能举一反三
- 5-7: 基本正确，但缺少细节或深度
- 1-4: 回答偏题，或存在明显错误"""),
    ("human", "请评分"),
])

# ── Final report prompt ──
REPORT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位资深的{position}面试官。请基于以下模拟面试记录，生成一份综合面试评估报告。

**面试岗位**：{position}
**面试方向**：{topic}
**面试难度**：{difficulty}
**总轮次**：{rounds}

**面试问答记录**：
{qa_records}

请从以下方面评估并输出 JSON（不要输出其他内容）：
{{
  "overall_score": 0-100 的整数综合评分,
  "summary": "总体评价（2-3句话）",
  "strengths": ["强项1", "强项2", "强项3"],
  "weaknesses": ["待改进1", "待改进2", "待改进3"],
  "technical_score": 技术能力评分(0-10),
  "communication_score": 沟通表达评分(0-10),
  "problem_solving_score": 解决问题能力评分(0-10),
  "suggestion": "针对性提升建议（2-3句话）"
}}"""),
    ("human", "请评估"),
])


@dataclass
class MockInterviewSession:
    """模拟面试会话"""
    session_id: str
    position: str = "全栈开发工程师"
    topic: str = "综合技术面试"
    difficulty: str = "medium"
    max_rounds: int = 5
    round_num: int = 0
    qa_history: list = field(default_factory=list)  # [{"q":"...", "a":"...", "score": n}, ...]
    current_question: str = ""

    STATUS: str = "idle"  # idle / waiting_answer / evaluating / finished

    _llm: Optional[ChatOpenAI] = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=assistant_config.llm_model,
                temperature=0.7,
                api_key=assistant_config.deepseek_api_key,
                base_url=assistant_config.deepseek_base_url,
            )
        return self._llm

    def get_difficulty_label(self) -> str:
        labels = {"easy": "初级", "medium": "中级", "hard": "高级"}
        return labels.get(self.difficulty, "中级")

    def _history_text(self) -> str:
        if not self.qa_history:
            return "（暂无历史记录）"
        lines = []
        for i, qa in enumerate(self.qa_history, 1):
            lines.append(f"Q{i}: {qa['q']}")
            if qa.get('a'):
                lines.append(f"A{i}: {qa['a']}")
        return "\n".join(lines)

    async def generate_question(self) -> str:
        """生成下一道面试题"""
        self.round_num += 1
        chain = QUESTION_PROMPT | self.llm
        response = await chain.ainvoke({
            "position": self.position,
            "topic": self.topic,
            "difficulty": self.get_difficulty_label(),
            "round_num": self.round_num,
            "max_rounds": self.max_rounds,
            "history": self._history_text(),
        })
        question = response.content.strip()
        self.current_question = question
        self.STATUS = "waiting_answer"
        self.qa_history.append({"q": question, "a": "", "score": 0, "evaluation": {}})
        return question

    async def evaluate_answer(self, answer: str) -> dict:
        """评估当前回答"""
        if not self.qa_history:
            return {"error": "没有当前题目"}

        self.qa_history[-1]["a"] = answer
        chain = EVALUATION_PROMPT | self.llm
        response = await chain.ainvoke({
            "position": self.position,
            "question": self.current_question,
            "answer": answer,
            "difficulty": self.get_difficulty_label(),
        })
        content = response.content.strip()
        # 提取 JSON
        try:
            # 尝试直接解析
            evaluation = json.loads(content)
        except json.JSONDecodeError:
            # 尝试提取 JSON 块
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    evaluation = json.loads(match.group())
                except json.JSONDecodeError:
                    evaluation = {"score": 0, "comment": "评分解析失败", "correctness": "", "depth": "", "communication": ""}
            else:
                evaluation = {"score": 0, "comment": "评分解析失败", "correctness": "", "depth": "", "communication": ""}

        self.qa_history[-1]["score"] = evaluation.get("score", 0)
        self.qa_history[-1]["evaluation"] = evaluation

        if self.round_num >= self.max_rounds:
            self.STATUS = "finished"
        else:
            self.STATUS = "idle"

        return evaluation

    async def generate_report(self) -> dict:
        """生成最终评估报告"""
        qa_text = "\n\n".join([
            f"第{i+1}轮\nQ: {qa['q']}\nA: {qa['a'] or '(未回答)'}\n评分: {qa.get('score', '-')}"
            for i, qa in enumerate(self.qa_history)
        ])

        chain = REPORT_PROMPT | self.llm
        response = await chain.ainvoke({
            "position": self.position,
            "topic": self.topic,
            "difficulty": self.get_difficulty_label(),
            "rounds": len(self.qa_history),
            "qa_records": qa_text,
        })
        content = response.content.strip()
        try:
            report = json.loads(content)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                try:
                    report = json.loads(match.group())
                except json.JSONDecodeError:
                    report = {"overall_score": 0, "summary": "报告生成失败", "strengths": [], "weaknesses": []}
            else:
                report = {"overall_score": 0, "summary": "报告生成失败", "strengths": [], "weaknesses": []}

        self.STATUS = "finished"
        return report

    def to_summary(self) -> dict:
        """导出会话摘要"""
        return {
            "session_id": self.session_id,
            "position": self.position,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "max_rounds": self.max_rounds,
            "round_num": self.round_num,
            "status": self.STATUS,
            "current_question": self.current_question,
            "qa_history": self.qa_history,
        }


# ── 全局会话管理 ──
_mock_sessions: dict[str, MockInterviewSession] = {}


def get_mock_session(session_id: str) -> Optional[MockInterviewSession]:
    return _mock_sessions.get(session_id)


def create_mock_session(session_id: str, position: str, topic: str, difficulty: str, max_rounds: int) -> MockInterviewSession:
    session = MockInterviewSession(
        session_id=session_id,
        position=position,
        topic=topic,
        difficulty=difficulty,
        max_rounds=max_rounds,
    )
    _mock_sessions[session_id] = session
    return session


def delete_mock_session(session_id: str):
    _mock_sessions.pop(session_id, None)
