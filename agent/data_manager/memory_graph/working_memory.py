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

    def __init__(self, agent_name: str, consolidate_interval: int = 30):
        self.agent_name = agent_name
        # 原始条目和压缩摘要分开存储
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        base_dir = os.path.join(str(project_root), "bots", agent_name)
        self._raw_path = os.path.join(base_dir, "working_memory_raw.json")
        self._summary_path = os.path.join(base_dir, "working_memory_summary.md")

        self.context: Dict[str, Any] = {}
        self.timeline: List[Dict[str, Any]] = []  # 仅原始条目
        self.consolidated_summary: str = ""  # 滚动压缩的完整摘要（独立存储）
        self.skeleton_summary: str = ""  # crystallize 后保留的骨架上下文，仅供 Agent 提示词使用
        self.consolidate_count_since_crystallize: int = 0  # 跨任务持久化的 crystallize 门槛计数器
        self.outcome: Optional[Dict[str, Any]] = None
        
        # 滚动压缩配置
        self.consolidate_interval = max(20, consolidate_interval)
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
        """crystallize 完成后清空缓冲区，但保留摘要和最近上下文。"""
        self.context = {}
        # 保留最后 5 条 timeline 提供连续性上下文
        self.timeline = self.timeline[-5:] if len(self.timeline) > 5 else self.timeline
        # consolidated_summary 保留不重置——它是滚动压缩的累积产物
        self.outcome = None
        self._save()

    # ==================== 写入 ====================

    def append(self, entry_type: str, content: str, detail: str = None,
               game_state: Dict[str, Any] = None, metadata: Dict[str, Any] = None,
               preserve: bool = False, consolidate_weight: int = 1):
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
            consolidate_weight: 计入 consolidate 触发的权重。
                1 = 正常计数（action, reasoning 等）
                0 = 不计数（observation — 由 EventTicker/PerceptionLLM 写入，
                    不应因为"周围路过几只羊"就触发记忆压缩）
        """
        entry = {
            "id": uuid.uuid4().hex,
            "timestamp": time.time(),
            "type": entry_type,
            "content": content,
            "consolidate_weight": consolidate_weight,
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
        self._entries_since_last_consolidation += consolidate_weight
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
        """检查是否达到 2n 触发条件：accumulated weight >= 2 * interval。"""
        return self._entries_since_last_consolidation >= 2 * self.consolidate_interval

    def get_entries_for_consolidation(self):
        """
        返回待压缩的条目批次（2n 模式）。

        从 timeline 头部扫描，计数 consolidate_weight > 0 的条目，
        找到第 n 个的边界位置。边界内的 weight=0 条目一并包含。

        Returns:
            (consumed_entries, ""):
                consumed_entries: 需要被压缩的条目列表（前 n 个 weight>0 条目 + 夹带的 weight=0）
                第二个元素保持空字符串（接口兼容，新 prompt 不再使用 CURRENT_SUMMARY）
        """
        n = self.consolidate_interval
        count = 0
        boundary = -1
        for i, entry in enumerate(self.timeline):
            if entry.get("consolidate_weight", 1) > 0:
                count += 1
            if count >= n:
                boundary = i + 1
                break

        if boundary == -1:
            return [], ""

        consumed = list(self.timeline[:boundary])
        return consumed, ""

    def update_summary(self, new_summary: str, consumed_entries: List[Dict[str, Any]]):
        """
        追加新的压缩摘要（带 ID 标记），移除已消费的原始条目。

        新模型：每批独立总结，摘要追加到 consolidated_summary 末尾。
        被消费的原始条目从 timeline 中移除（其信息已融入摘要）。

        Args:
            new_summary: LLM 生成的摘要文本
            consumed_entries: 本次被消费的条目列表，通过 ID 匹配删除
        """
        ids_to_remove = {e.get("id") for e in consumed_entries}
        self.timeline = [e for e in self.timeline if e.get("id") not in ids_to_remove]
        self._entries_since_last_consolidation = sum(
            e.get("consolidate_weight", 1) for e in self.timeline
        )

        summary_id = uuid.uuid4().hex[:12]
        new_block = f"[consolidation:{summary_id}]\n{new_summary.strip()}"
        if self.consolidated_summary:
            self.consolidated_summary += "\n\n" + new_block
        else:
            self.consolidated_summary = new_block

        self._save()

    def parse_summary_entries(self) -> List[Dict[str, str]]:
        """
        将 consolidated_summary 解析为结构化列表。

        consolidated_summary 是连续追加的文本块，格式为：
            [consolidation:id1]
            content line 1
            content line 2

            [consolidation:id2]
            content line 3
            ...

        Returns:
            按顺序排列的列表，每项为 {"id": str, "content": str}
            空摘要返回空列表。
        """
        if not self.consolidated_summary.strip():
            return []

        entries = []
        current_id = None
        current_lines = []

        for line in self.consolidated_summary.split('\n'):
            stripped = line.strip()
            if stripped.startswith('[consolidation:') and stripped.endswith(']'):
                if current_id is not None:
                    content = '\n'.join(current_lines).strip()
                    if content:
                        entries.append({"id": current_id, "content": content})
                current_id = stripped[len('[consolidation:'):-len(']')]
                current_lines = []
            else:
                current_lines.append(line)

        if current_id is not None:
            content = '\n'.join(current_lines).strip()
            if content:
                entries.append({"id": current_id, "content": content})

        return entries

    def remove_summary_entries(self, count: int):
        """
        从 consolidated_summary 开头移除 N 个摘要条目。

        crystallize 消费前 n 个摘要条目后调用，保持 FIFO 顺序（最旧的先被消费）。

        Args:
            count: 要移除的条目数量（从头开始）
        """
        entries = self.parse_summary_entries()
        if not entries or count <= 0:
            return
        kept = entries[count:]

        if not kept:
            self.consolidated_summary = ""
        else:
            blocks = [f"[consolidation:{e['id']}]\n{e['content']}" for e in kept]
            self.consolidated_summary = "\n\n".join(blocks)

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

    def get_buffer_text(self, include_skeleton: bool = False) -> str:
        """
        将工作记忆格式化为可嵌入系统提示词的文本。
        使用轻量标记（无 ## 标题）避免在提示词中产生多余的标题层级。

        Args:
            include_skeleton: 若为 True，当无 timeline 和摘要时，返回骨架摘要。
                             仅 Agent 提示词使用；crystallize 调用时传 False。
        """
        if not self.timeline and not self.consolidated_summary:
            if include_skeleton and self.skeleton_summary:
                return f"▸ 近期概要\n{self.skeleton_summary}"
            return "（暂无工作记忆）"

        lines = []

        # 任务背景
        if self.context:
            goal = self.context.get('goal', '未知')
            lines.append(f"【当前目标】{goal}")
            if self.context.get('strategic_reasoning'):
                lines.append(f"【战略分析】{self.context['strategic_reasoning']}")
            if self.context.get('task_plan'):
                steps = '、'.join(self.context['task_plan'][:5])
                lines.append(f"【执行计划】{steps}")
            if self.context.get('environment'):
                lines.append(f"【环境】{self.context['environment']}")

        # 已压缩的滚动摘要
        if self.consolidated_summary:
            lines.append("")
            lines.append("▸ 经历摘要")
            lines.append(self.consolidated_summary)

        # 骨架摘要（crystallize 后保留的上下文，仅 Agent 提示词可见）
        if include_skeleton and self.skeleton_summary and not self.consolidated_summary:
            lines.append("")
            lines.append("▸ 近期概要")
            lines.append(self.skeleton_summary)

        # 尚未压缩的原始条目（最多显示最新 N 条，N=consolidate_interval）
        if self.timeline:
            visible = self.timeline[-self.consolidate_interval:]
            lines.append("")
            lines.append(f"▸ 最新记录（共 {len(self.timeline)} 条，显示最新 {len(visible)} 条）")
            for entry in visible:
                type_tag = entry.get("type", "unknown").upper()
                content = entry.get("content", "")
                preserved_tag = "[重要] " if entry.get("preserve") else ""
                line = f"· {preserved_tag}[{type_tag}] {content}"
                if entry.get("detail"):
                    line += f"\n  └ {entry['detail']}"
                meta = entry.get("metadata")
                if meta:
                    thinking = meta.get('thinking', '')
                    if thinking:
                        line += f"\n  └ 思考: {thinking}"
                    other = {k: v for k, v in meta.items() if k != 'thinking' and v}
                    if other:
                        line += f"\n  └ 附加: {'; '.join(f'{k}={v}' for k,v in other.items())}"
                snapshot_text = self._format_snapshot(entry.get("snapshot"))
                if snapshot_text:
                    line += f"\n  {snapshot_text.strip(' |')}"
                lines.append(line)

        # 结果
        if self.outcome:
            lines.append("")
            result_label = self.outcome.get('result', '未知')
            summary = self.outcome.get('summary', '')
            lines.append(f"【任务结果】{result_label}" + (f"：{summary}" if summary else ""))

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
            parts.append(f"第{snapshot['world_day'] + 1}天")
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
                "skeleton_summary": self.skeleton_summary,
                "consolidate_count_since_crystallize": self.consolidate_count_since_crystallize,
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
                self.skeleton_summary = data.get("skeleton_summary", "")
                self.consolidate_count_since_crystallize = data.get("consolidate_count_since_crystallize", 0)
            except Exception as e:
                logger.warning(f"工作记忆原始数据加载失败，将重新开始: {e}")
            
        if os.path.exists(self._summary_path):
            try:
                with open(self._summary_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    self.consolidated_summary = content
            except Exception as e:
                logger.warning(f"工作记忆摘要加载失败: {e}")
