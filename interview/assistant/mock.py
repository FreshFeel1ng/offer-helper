"""
模拟面试模块 v2
- 使用 DeepSeek 根据职位/话题自动出题
- 出题时参考面试者历史薄弱点，靶向提升
- 每轮生成标准答案供面试者学习
- 语音/文字回答，AI 逐轮评分
- 面试结束后生成综合评分报告 + 学习对比
"""

import json
import time
from typing import AsyncGenerator, Optional
from dataclasses import dataclass, field

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from .config import config as assistant_config


# ── Weakness-aware question prompt ──
QUESTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位专业的{position}面试官，正在进行一场{difficulty}难度的模拟面试。

当前是第 {round_num} / {max_rounds} 轮。
面试主题/岗位：{position}
面试重点方向：{topic}

{weakness_instruction}

已问过的问题和回答：
{history}

请根据以上信息，生成下一道面试问题。要求：
1. 如果展示了历史薄弱点，优先针对薄弱维度出题，帮助候选人提升
2. 问题要覆盖考察维度（技术基础、项目经验、系统设计、行为面试等）
3. 如果前面问过某个方向，下一题换另一个方向
4. 难度逐步递增
5. 问题要有场景感，具体而不宽泛
6. 如果是最后一轮，可以问综合性问题
7. 只输出问题本身，不要加任何前缀说明"""),
    ("human", "请出下一道面试题"),
])

# ── Standard answer prompt ──
STANDARD_ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一位资深的{position}面试官。请为以下面试题提供一个高分标准答案。

**面试题**：{question}
**面试难度**：{difficulty}
**候选人当前回答（供参考优缺点）**：{user_answer}

请从以下结构输出答案：
1. 核心要点（2-3句话总结）
2. 详细回答（结构化、有层次）
3. 加分项提示（可以额外提到的点）

输出格式（JSON）：
{{
  "key_points": "核心要点总结",
  "detailed_answer": "详细回答（可多段落）",
  "bonus_tips": "加分项提示"
}}

只输出 JSON，不要其他内容。"""),
    ("human", "请生成标准答案"),
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


def _get_historical_weaknesses(position: str) -> str:
    """从数据库中获取历史薄弱点，用于靶向出题"""
    try:
        from boss.state import list_mock_interviews
        records = list_mock_interviews(limit=10)
        all_weaknesses = []
        for r in records:
            if r.get("position", "") != position:
                continue
            try:
                ev = json.loads(r.get("overall_evaluation", "{}"))
            except Exception:
                ev = {}
            weaks = ev.get("weaknesses", [])
            for w in weaks:
                if w not in all_weaknesses:
                    all_weaknesses.append(w)
        if all_weaknesses:
            return "**历史薄弱点（来自过往面试记录，请重点针对这些方向出题）**：\n" + "\n".join(
                f"  - {w}" for w in all_weaknesses[:5]
            )
    except Exception:
        pass
    return ""


@dataclass
class MockInterviewSession:
    """模拟面试会话"""
    session_id: str
    position: str = "全栈开发工程师"
    topic: str = "综合技术面试"
    difficulty: str = "medium"
    max_rounds: int = 5
    round_num: int = 0
    qa_history: list = field(default_factory=list)
    current_question: str = ""

    STATUS: str = "idle"

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
                lines.append(f"评分: {qa.get('score', '-')}/10")
        return "\n".join(lines)

    async def generate_question(self) -> str:
        """生成下一道面试题（参考历史薄弱点）"""
        self.round_num += 1
        weakness_instruction = _get_historical_weaknesses(self.position)
        if not weakness_instruction and self.round_num == 1:
            weakness_instruction = "（暂无历史薄弱点记录，请根据岗位要求正常出题）"

        chain = QUESTION_PROMPT | self.llm
        response = await chain.ainvoke({
            "position": self.position,
            "topic": self.topic,
            "difficulty": self.get_difficulty_label(),
            "round_num": self.round_num,
            "max_rounds": self.max_rounds,
            "history": self._history_text(),
            "weakness_instruction": weakness_instruction,
        })
        question = response.content.strip()
        self.current_question = question
        self.STATUS = "waiting_answer"
        self.qa_history.append({
            "q": question, "a": "", "score": 0,
            "evaluation": {}, "standard_answer": {},
        })
        return question

    async def evaluate_answer(self, answer: str) -> dict:
        """评估当前回答并生成标准答案"""
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
        try:
            evaluation = json.loads(content)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', content, re.DOTALL)
            evaluation = json.loads(match.group()) if match else {}
        if not isinstance(evaluation, dict):
            evaluation = {}

        self.qa_history[-1]["score"] = evaluation.get("score", 0)
        self.qa_history[-1]["evaluation"] = evaluation

        # ── 生成标准答案 ──
        try:
            sa_chain = STANDARD_ANSWER_PROMPT | self.llm
            sa_resp = await sa_chain.ainvoke({
                "position": self.position,
                "question": self.current_question,
                "user_answer": answer,
                "difficulty": self.get_difficulty_label(),
            })
            sa_content = sa_resp.content.strip()
            try:
                standard = json.loads(sa_content)
            except json.JSONDecodeError:
                import re
                match = re.search(r'\{.*\}', sa_content, re.DOTALL)
                standard = json.loads(match.group()) if match else {}
            if not isinstance(standard, dict):
                standard = {}
            self.qa_history[-1]["standard_answer"] = standard
            print(f"[Mock面试] 标准答案已生成 ({len(standard.get('detailed_answer', ''))}字)")
        except Exception as e:
            print(f"[Mock面试] 生成标准答案失败: {e}")
            self.qa_history[-1]["standard_answer"] = {"key_points": "", "detailed_answer": "", "bonus_tips": ""}

        if self.round_num >= self.max_rounds:
            self.STATUS = "finished"
        else:
            self.STATUS = "idle"

        return evaluation

    async def generate_report(self) -> dict:
        """生成最终评估报告"""
        qa_text = "\n\n".join([
            f"第{i+1}轮\n"
            f"Q: {qa['q']}\n"
            f"A: {qa['a'] or '(未回答)'}\n"
            f"评分: {qa.get('score', '-')}/10\n"
            f"标准答案要点: {qa.get('standard_answer', {}).get('key_points', '-')}"
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
            report = json.loads(match.group()) if match else {}

        self.STATUS = "finished"
        return report

    def to_summary(self) -> dict:
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
