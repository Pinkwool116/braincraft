"""
工作记忆缓冲区（Working Memory Buffer）

任务生命周期内的结构化日志缓冲区，类似于人的"短期记忆/工作台"。
在任务执行过程中积累原始体验，任务结束后由反思过程消费并蒸馏为长期记忆图谱节点。

生命周期：随任务创建而生，随反思（crystallize）完成后清空。
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class WorkingMemoryBuffer:
    """
    工作记忆：任务执行期间的临时体验缓冲区。

    不是图，是线性追加的日志。人在做事时先体验再回忆。
    所有原始事件在这里积累，直到任务边界点触发反思，
    由 LLM 将其蒸馏为长期记忆图谱中的节点和边。
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self._persist_path = os.path.join("bots", agent_name, "working_memory.json")
        
        self.context: Dict[str, Any] = {}
        self.timeline: List[Dict[str, Any]] = []
        self.outcome: Optional[Dict[str, Any]] = None
        
        # 尝试从磁盘恢复（防崩溃丢失）
        self._load()

    # ==================== 生命周期 ====================

    def begin_task(self, goal: str, environment_snapshot: str = ""):
        """
        开始一个新的工作记忆会话。在任务开始时调用。
        如果上一次的缓冲区还有内容（未被 crystallize），会被归档保留。
        """
        if self.timeline:
            logger.warning("工作记忆缓冲区上一轮未清空，可能丢失了一次 crystallize，将覆盖。")
        
        self.context = {
            "goal": goal,
            "environment": environment_snapshot,
            "started_at": time.time(),
        }
        self.timeline = []
        self.outcome = None
        self._save()

    def end_task(self, result: str, summary: str = ""):
        """
        标记任务结束。result 应为 "success" / "failure" / "abandoned" 之一。
        """
        self.outcome = {
            "result": result,
            "summary": summary,
            "ended_at": time.time(),
        }
        self._save()

    def clear(self):
        """反思（crystallize）完成后清空缓冲区。"""
        self.context = {}
        self.timeline = []
        self.outcome = None
        self._save()

    # ==================== 写入 ====================

    def append(self, entry_type: str, content: str, detail: str = None):
        """
        向时间线追加一条记录。

        Args:
            entry_type: 条目类型，如 "action", "observation", "failure", "interaction", "discovery"
            content: 发生了什么
            detail: 可选的补充细节（如错误信息、代码片段摘要等）
        """
        entry = {
            "timestamp": time.time(),
            "type": entry_type,
            "content": content,
        }
        if detail:
            entry["detail"] = detail
        
        self.timeline.append(entry)
        self._save()

    # ==================== 读取 ====================

    @property
    def is_active(self) -> bool:
        """当前是否有活跃的工作记忆会话。"""
        return bool(self.context)

    @property
    def has_content(self) -> bool:
        """缓冲区是否有可供反思的内容。"""
        return bool(self.timeline)

    def get_buffer_text(self) -> str:
        """
        将工作记忆格式化为 LLM 可消费的文本，供反思（crystallize）使用。
        """
        if not self.timeline:
            return ""

        lines = []

        # 任务背景
        if self.context:
            lines.append(f"## 任务背景")
            lines.append(f"目标: {self.context.get('goal', '未知')}")
            if self.context.get('environment'):
                lines.append(f"环境: {self.context['environment']}")
            lines.append("")

        # 时间线
        lines.append(f"## 经历时间线 ({len(self.timeline)} 条记录)")
        for entry in self.timeline:
            type_tag = entry.get("type", "unknown").upper()
            content = entry.get("content", "")
            line = f"- [{type_tag}] {content}"
            if entry.get("detail"):
                line += f" | 详情: {entry['detail']}"
            lines.append(line)
        lines.append("")

        # 结果
        if self.outcome:
            lines.append(f"## 任务结果")
            lines.append(f"结果: {self.outcome.get('result', '未知')}")
            if self.outcome.get('summary'):
                lines.append(f"总结: {self.outcome['summary']}")

        return "\n".join(lines)

    # ==================== 持久化 ====================

    def _save(self):
        """持久化到磁盘（防崩溃丢失）。"""
        try:
            os.makedirs(os.path.dirname(self._persist_path), exist_ok=True)
            data = {
                "context": self.context,
                "timeline": self.timeline,
                "outcome": self.outcome,
            }
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"工作记忆持久化失败: {e}")

    def _load(self):
        """从磁盘加载（崩溃恢复）。"""
        if not os.path.exists(self._persist_path):
            return
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.context = data.get("context", {})
            self.timeline = data.get("timeline", [])
            self.outcome = data.get("outcome")
        except Exception as e:
            logger.warning(f"工作记忆加载失败，将重新开始: {e}")
