"""
工作记忆缓冲区（Working Memory Buffer）

任务生命周期内的结构化日志缓冲区，类似于人的"短期记忆/工作台"。
在任务执行过程中积累原始体验，任务结束后由反思过程消费并蒸馏为长期记忆图谱节点。

生命周期：随任务创建而生，随反思（crystallize）完成后清空。
"""

import os
import json
import time
import uuid
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class WorkingMemoryBuffer:
    """
    工作记忆：任务执行期间的临时体验缓冲区。

    不是图，是线性追加的日志。人在做事时先体验再回忆。
    所有原始事件在这里积累，直到任务边界点触发反思，
    由 LLM 将其蒸馏为长期记忆图谱中的节点和边。

    支持滚动压缩：原始条目和压缩摘要分开存储。
    每 N 条新记录触发一次全量压缩：将当前摘要与新增条目一起交给 LLM，
    LLM 输出新的完整摘要全量替换旧摘要，已消费的原始条目随即移除。
    """

    def __init__(self, agent_name: str, consolidate_interval: int = 5):
        self.agent_name = agent_name
        # 原始条目和压缩摘要分开存储
        self._raw_path = os.path.join("bots", agent_name, "working_memory_raw.json")
        self._summary_path = os.path.join("bots", agent_name, "working_memory_summary.md")
        
        self.context: Dict[str, Any] = {}
        self.timeline: List[Dict[str, Any]] = []  # 仅原始条目
        self.consolidated_summary: str = ""  # 滚动压缩的完整摘要（独立存储）
        self.outcome: Optional[Dict[str, Any]] = None
        
        # 滚动压缩配置
        self.consolidate_interval = max(3, consolidate_interval)
        self._entries_since_last_consolidation = 0
        
        # 尝试从磁盘恢复（防崩溃丢失）
        self._load()

    # ==================== 生命周期 ====================

    def begin_task(self, goal: str, environment_snapshot: str = "",
                   task_plan: List[str] = None, strategic_reasoning: str = ""):
        """
        开始一个新的工作记忆会话。在任务开始时调用。
        如果上一次的缓冲区还有内容（未被 crystallize），会被归档保留。

        Args:
            goal: 任务目标描述
            environment_snapshot: 当前环境状态快照
            task_plan: 高层拆分的步骤列表（用于上下文注入）
            strategic_reasoning: 高层的战略推理（用于上下文注入）
        """
        if self.timeline:
            logger.warning("工作记忆缓冲区上一轮未清空，可能丢失了一次 crystallize，将覆盖。")
        
        self.context = {
            "goal": goal,
            "environment": environment_snapshot,
            "started_at": time.time(),
        }
        if task_plan:
            self.context["task_plan"] = task_plan
        if strategic_reasoning:
            self.context["strategic_reasoning"] = strategic_reasoning
        
        self.timeline = []
        self.consolidated_summary = ""
        self.outcome = None
        self._entries_since_last_consolidation = 0
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
        self.consolidated_summary = ""
        self.outcome = None
        self._save()

    # ==================== 写入 ====================

    def append(self, entry_type: str, content: str, detail: str = None,
               game_state: Dict[str, Any] = None, metadata: Dict[str, Any] = None,
               preserve: bool = False):
        """
        向时间线追加一条记录。

        Args:
            entry_type: 条目类型，如 "action", "observation", "failure", "interaction",
                        "discovery", "reasoning", "code_attempt"
            content: 发生了什么
            detail: 可选的补充细节（如错误信息、代码片段摘要等）
            game_state: 可选的当前游戏状态快照，用于丰富记忆上下文
            metadata: 可选的结构化补充数据（如LLM推理、关键代码调用等）
            preserve: 若为True，该条目在滚动压缩时不会被压缩，原封保留
        """
        entry = {
            "id": uuid.uuid4().hex,
            "timestamp": time.time(),
            "type": entry_type,
            "content": content,
        }
        if detail:
            entry["detail"] = detail
        if game_state:
            entry["snapshot"] = self._extract_snapshot(game_state)
        if metadata:
            entry["metadata"] = metadata
        if preserve:
            entry["preserve"] = True
        
        self.timeline.append(entry)
        self._entries_since_last_consolidation += 1
        self._save()

    @staticmethod
    def _extract_snapshot(game_state: Dict[str, Any]) -> Dict[str, Any]:
        """从完整的 game_state 中提取关键字段作为快照，与 code generation 提示词中的游戏状态变量对齐。"""
        snapshot = {}
        # 位置
        if game_state.get("position"):
            pos = game_state["position"]
            snapshot["position"] = {
                "x": round(pos.get("x", 0), 1),
                "y": round(pos.get("y", 0), 1),
                "z": round(pos.get("z", 0), 1),
            }
        # 标量状态字段
        for key in ("biome", "health", "food", "time_label", "time_of_day",
                    "world_day", "weather", "dimension", "gamemode"):
            val = game_state.get(key)
            if val is not None:
                snapshot[key] = val
        # 物品栏与装备
        inv = game_state.get("inventory")
        if inv:
            snapshot["inventory"] = inv
        equip = game_state.get("equipment")
        if equip:
            snapshot["equipment"] = equip
        # 紧邻方块（surrounding_blocks: below/legs/head/firstAbove）
        surrounding = game_state.get("surrounding_blocks")
        if surrounding:
            snapshot["surrounding_blocks"] = {
                "below": surrounding.get("below", "unknown"),
                "legs": surrounding.get("legs", "unknown"),
                "head": surrounding.get("head", "unknown"),
                "above": surrounding.get("firstAbove", "none"),
            }
        # 附近方块（取唯一名称列表，避免大量重复数据）
        nearby_blocks = game_state.get("nearby_blocks")
        if nearby_blocks and isinstance(nearby_blocks, list):
            seen = set()
            names = []
            for b in nearby_blocks:
                name = b.get("name") if isinstance(b, dict) else str(b)
                if name and name not in seen:
                    seen.add(name)
                    names.append(name)
            if names:
                snapshot["nearby_blocks"] = names
        # 附近实体
        nearby_entities = game_state.get("nearby_entities")
        if nearby_entities and isinstance(nearby_entities, list):
            entity_list = []
            for e in nearby_entities:
                if isinstance(e, dict):
                    etype = e.get("type", "")
                    ename = e.get("name", etype)
                    if etype == "player":
                        entity_list.append(f"player:{ename}")
                    elif etype and etype != "item":
                        entity_list.append(etype)
                else:
                    entity_list.append(str(e))
            if entity_list:
                snapshot["nearby_entities"] = list(dict.fromkeys(entity_list))  # 去重保序
        return snapshot

    # ==================== 滚动压缩 ====================

    def should_consolidate(self) -> bool:
        """当前是否应该触发一次滚动压缩。"""
        return self._entries_since_last_consolidation >= self.consolidate_interval

    def get_entries_for_consolidation(self):
        """
        返回待压缩的新增原始条目和当前压缩摘要，供 LLM 全量压缩使用。

        Returns:
            (new_entries, current_summary): 
                new_entries: 需要被压缩的记录列表，目前是取时间线上尚未压缩的所有条目
                current_summary: 当前的滚动压缩摘要文本（可能为空字符串）
        """
        # 返回当前缓冲区内所有的记录进行压缩
        new_entries = list(self.timeline)
        return new_entries, self.consolidated_summary

    def update_summary(self, new_summary: str, consumed_entries: List[Dict[str, Any]]):
        """
        用 LLM 生成的新摘要完全替换旧摘要，并移除已被消费的原始条目。

        新模型：旧摘要 + 新原始条目 → LLM → 新的完整摘要，全量替换。
        被消费的原始条目从 timeline 中移除（其信息已融入摘要）。
        
        Args:
            new_summary: LLM 生成的新压缩摘要
            consumed_entries: 需要被删除的、已被包含在本次压缩中的条目列表。
                              通过匹配 ID 来真实删除目标。
        """
        ids_to_remove = {e.get("id") for e in consumed_entries}
        self.timeline = [e for e in self.timeline if e.get("id") not in ids_to_remove]
        self._entries_since_last_consolidation = len(self.timeline)

        self.consolidated_summary = new_summary.strip()
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
            if self.context.get('strategic_reasoning'):
                lines.append(f"战略分析: {self.context['strategic_reasoning']}")
            if self.context.get('task_plan'):
                lines.append("执行计划:")
                for i, step in enumerate(self.context['task_plan'], 1):
                    lines.append(f"  {i}. {step}")
            if self.context.get('environment'):
                lines.append(f"环境: {self.context['environment']}")
            lines.append("")

        # 已压缩的滚动摘要
        if self.consolidated_summary:
            lines.append(f"## 已整理的经历摘要")
            lines.append(self.consolidated_summary)
            lines.append("")

        # 尚未压缩的原始条目
        if self.timeline:
            lines.append(f"## 最新经历 ({len(self.timeline)} 条记录)")
            for entry in self.timeline:
                type_tag = entry.get("type", "unknown").upper()
                content = entry.get("content", "")
                preserved_tag = "[重要/PRESERVED] " if entry.get("preserve") else ""
                line = f"- {preserved_tag}[{type_tag}] {content}"
                if entry.get("detail"):
                    line += f"\n  详情: {entry['detail']}"
                # 展示 metadata 中的结构化信息
                meta = entry.get("metadata")
                if meta:
                    meta_parts = [f"{k}: {v}" for k, v in meta.items()
                                  if v and k not in ('snapshot',)]
                    if meta_parts:
                        line += f"\n  附加: {'; '.join(meta_parts)}"
                snapshot_text = self._format_snapshot(entry.get("snapshot"))
                if snapshot_text:
                    line += f"\n  {snapshot_text.strip(' |')}"
                lines.append(line)
            lines.append("")

        # 结果
        if self.outcome:
            lines.append(f"## 任务结果")
            lines.append(f"结果: {self.outcome.get('result', '未知')}")
            if self.outcome.get('summary'):
                lines.append(f"总结: {self.outcome['summary']}")

        return "\n".join(lines)

    @staticmethod
    def _format_snapshot(snapshot: Optional[Dict[str, Any]]) -> str:
        """将快照格式化为追加在日志行末尾的简洁文本。"""
        if not snapshot:
            return ""
        parts = []
        pos = snapshot.get("position")
        if pos:
            parts.append(f"位置:({pos.get('x',0)},{pos.get('y',0)},{pos.get('z',0)})")
        if snapshot.get("biome"):
            parts.append(f"群系:{snapshot['biome']}")
        if snapshot.get("health") is not None:
            parts.append(f"生命:{snapshot['health']}")
        if snapshot.get("food") is not None:
            parts.append(f"饥饿:{snapshot['food']}")
        if snapshot.get("time_label"):
            parts.append(f"时间:{snapshot['time_label']}")
        if snapshot.get("world_day") is not None:
            parts.append(f"第{snapshot['world_day']}天")
        if snapshot.get("weather"):
            parts.append(f"天气:{snapshot['weather']}")
        if snapshot.get("dimension"):
            parts.append(f"维度:{snapshot['dimension']}")
        inv = snapshot.get("inventory")
        if inv:
            items = [f"{k}x{v}" for k, v in inv.items()]
            parts.append(f"背包:[{','.join(items)}]")
        equip = snapshot.get("equipment")
        if equip:
            equipped = [f"{slot}={name}" for slot, name in equip.items() if name]
            if equipped:
                parts.append(f"装备:[{','.join(equipped)}]")
        surr = snapshot.get("surrounding_blocks")
        if surr:
            parts.append(
                f"紧邻[脚下非空气方块:{surr.get('below','?')} 腿部全息方块:{surr.get('legs','?')} "
                f"头部方块:{surr.get('head','?')} 头顶第一个固体方块:{surr.get('above','?')}]"
            )
        nb = snapshot.get("nearby_blocks")
        if nb:
            parts.append(f"附近方块:[{','.join(nb[:12])}{'...' if len(nb)>12 else ''}]")
        ne = snapshot.get("nearby_entities")
        if ne:
            parts.append(f"附近实体:[{','.join(ne[:8])}{'...' if len(ne)>8 else ''}]")
        return (" | 状态: " + ", ".join(parts)) if parts else ""

    # ==================== 持久化 ====================

    def _save(self):
        """持久化到磁盘（防崩溃丢失）。原始条目和压缩摘要分别存储。"""
        try:
            os.makedirs(os.path.dirname(self._raw_path), exist_ok=True)
            # 原始条目文件
            raw_data = {
                "context": self.context,
                "timeline": self.timeline,
                "outcome": self.outcome,
                "entries_since_last_consolidation": self._entries_since_last_consolidation,
            }
            with open(self._raw_path, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, indent=2, ensure_ascii=False)
            # 压缩摘要文件
            with open(self._summary_path, "w", encoding="utf-8") as f:
                f.write(self.consolidated_summary)
        except Exception as e:
            logger.error(f"工作记忆持久化失败: {e}")

    def _load(self):
        """从磁盘加载（崩溃恢复）。"""
        if os.path.exists(self._raw_path):
            try:
                with open(self._raw_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.context = data.get("context", {})
                self.timeline = data.get("timeline", [])
                self.outcome = data.get("outcome")
                self._entries_since_last_consolidation = data.get("entries_since_last_consolidation", 0)
            except Exception as e:
                logger.warning(f"工作记忆原始数据加载失败，将重新开始: {e}")
            
        if os.path.exists(self._summary_path):
            try:
                with open(self._summary_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self.consolidated_summary = content
            except Exception as e:
                logger.warning(f"工作记忆摘要加载失败: {e}")
