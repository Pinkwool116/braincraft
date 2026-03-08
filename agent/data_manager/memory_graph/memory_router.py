"""
记忆路由器（MemoryRouter） - 大脑与记忆系统的统一接口

核心设计：积累 → 反思 → 沉淀
- 工作记忆（WorkingMemoryBuffer）：任务执行时的临时缓冲区，线性追加原始体验
- 长期记忆（GraphEngine）：经过反思蒸馏后的结构化图谱
- 唯一的转化通道：crystallize() 在任务边界点将工作记忆蒸馏为图谱节点和边

任务执行时往工作记忆"写日记"，任务结束后通过 LLM 反思把日记"蒸馏"成图谱。
"""

import logging
import json
import re
import os
from typing import Dict, Any, List, Optional

from .graph_engine import GraphEngine
from .graph_retriever import GraphRetriever
from .working_memory import WorkingMemoryBuffer
from .graph_types import NodeType, EdgeRelation
from prompts.prompt_logger import PromptLogger

logger = logging.getLogger(__name__)


class MemoryRouter:
    """
    大脑（Brain）与记忆系统的统一接口。
    管理工作记忆（短期）和图谱记忆（长期）两个层级。
    """

    def __init__(self, agent_name: str, enable_logging: bool = True):
        self.agent_name = agent_name
        
        # 长期记忆：图谱
        self.engine = GraphEngine(agent_name)
        self.retriever = GraphRetriever(self.engine)
        
        # 短期记忆：工作记忆缓冲区
        self.working_memory = WorkingMemoryBuffer(agent_name)
        
        # 日志
        self.prompt_logger = PromptLogger("bots", agent_name, enabled=enable_logging)
        
        # 预加载反思提示词模板
        prompt_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "prompts", "memory", "memory_graph_extraction.txt"
        )
        self.extraction_prompt_template = ""
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.extraction_prompt_template = f.read()
        except Exception as e:
            logger.warning(f"未能加载记忆图谱抽取提示词模板: {e}")

        logger.info(f"MemoryRouter 初始化完成 '{agent_name}'")

    # ==================== 工作记忆接口 ====================

    def begin_task(self, goal: str, environment_snapshot: str = ""):
        """
        任务开始时调用，初始化工作记忆会话。
        
        Args:
            goal: 任务目标描述
            environment_snapshot: 当前环境状态快照（位置、生物群系等）
        """
        self.working_memory.begin_task(goal, environment_snapshot)

    def log(self, entry_type: str, content: str, detail: str = None):
        """
        向工作记忆追加一条记录（替代旧的 experience() 方法）。
        
        在任务执行过程中调用，无需关心这条记录未来会变成什么图谱节点。
        
        Args:
            entry_type: "action" | "observation" | "failure" | "interaction" | "discovery"
            content: 发生了什么
            detail: 可选补充信息
        """
        self.working_memory.append(entry_type, content, detail)

    def end_task(self, result: str, summary: str = ""):
        """
        任务结束时调用。result: "success" | "failure" | "abandoned"
        """
        self.working_memory.end_task(result, summary)

    # ==================== 反思（工作记忆 → 长期记忆） ====================

    async def crystallize(self, llm_wrapper) -> None:
        """
        反思过程：将工作记忆蒸馏为长期记忆图谱节点和边。
        在任务边界点（结束/放弃）调用。
        
        流程：
        1. 收集工作记忆缓冲区内容
        2. 检索已有图谱中的相关上下文（让 LLM 知道"我已经知道什么"）
        3. 调用 LLM 从经历中提炼值得长期记住的内容
        4. 将结果整合到图谱
        5. 清空工作记忆
        """
        if not self.working_memory.has_content:
            logger.debug("工作记忆为空，跳过 crystallize")
            return

        if not self.extraction_prompt_template:
            logger.error("缺少提示词模板，跳过 crystallize")
            return

        buffer_text = self.working_memory.get_buffer_text()
        
        # 检索已有的相关记忆，供 LLM 参考避免重复
        existing_context = self._get_existing_context_for_reflection()

        # 构建反思提示词
        prompt = self.extraction_prompt_template.replace("{buffer_text}", buffer_text)
        prompt = prompt.replace("{existing_context}", existing_context)

        prompt_file = self.prompt_logger.log_prompt(
            prompt=prompt,
            brain_layer="memory_graph",
            prompt_type="crystallize"
        )

        try:
            response = await llm_wrapper.send_request(
                [{"role": "user", "content": prompt}]
            )
            self.prompt_logger.update_response(prompt_file, response)

            match = re.search(r'\{.*\}', response, re.DOTALL | re.MULTILINE)
            if match:
                data = json.loads(match.group(0))
                self._integrate_llm_extraction(data)
                logger.info("crystallize 完成：工作记忆已蒸馏为图谱节点")
            else:
                logger.warning("crystallize: LLM 返回中未找到 JSON")

        except Exception as e:
            logger.error(f"crystallize 失败: {e}", exc_info=True)
            return  # 失败时不清空工作记忆，下次可以重试

        # 成功后清空工作记忆
        self.working_memory.clear()

    def _get_existing_context_for_reflection(self) -> str:
        """获取已有图谱中的相关上下文，用于反思时避免重复。"""
        # 取最近的若干 episode 和 pattern 节点概览
        episodes = self.engine.find_nodes_by_type(NodeType.EPISODE)
        patterns = self.engine.find_nodes_by_type(NodeType.PATTERN)
        
        lines = []
        if episodes:
            recent_episodes = sorted(episodes, key=lambda n: n.created_at, reverse=True)[:5]
            lines.append("已有经历:")
            for ep in recent_episodes:
                lines.append(f"  - {ep.content}")
        if patterns:
            recent_patterns = sorted(patterns, key=lambda n: n.created_at, reverse=True)[:5]
            lines.append("已有经验规则:")
            for pat in recent_patterns:
                lines.append(f"  - {pat.content}")
        
        return "\n".join(lines) if lines else "暂无已有记忆。"

    # ==================== 图谱整合 ====================

    def _integrate_llm_extraction(self, graph_data: dict):
        """将 LLM 提取的结构化 JSON 合并到图谱中。"""
        content_to_id = {}
        
        # 合并节点
        for n in graph_data.get("nodes", []):
            content = n.get("content")
            n_type = n.get("type", "event")
            if not content:
                continue
            
            # 去重：如果已有相同内容和类型的节点，复用并增加热度
            existing = [x for x in self.engine.find_nodes_by_type(n_type) if x.content == content]
            if existing:
                target_node = existing[0]
                content_to_id[content] = target_node.id
                target_node.access_count += 1
            else:
                metadata = n.get("metadata", {})
                new_node = self.engine.add_node(n_type, content, metadata)
                content_to_id[content] = new_node.id

        # 链接边关系
        for e in graph_data.get("edges", []):
            src_str = e.get("source")
            tgt_str = e.get("target")
            src_id = content_to_id.get(src_str)
            tgt_id = content_to_id.get(tgt_str)
            if src_id and tgt_id:
                relation = e.get("relation", EdgeRelation.RELATED_TO)
                weight = e.get("weight", 1.0)
                self.engine.add_edge(src_id, tgt_id, relation=relation, weight=weight)

    # ==================== 检索（长期记忆 → 提示词注入） ====================

    def retrieve_context(self, trigger_texts: List[str] = None, top_k: int = 8) -> str:
        """
        使用扩散激活算法检索相关记忆上下文，格式化为可注入提示词的文本。
        
        种子节点选择策略由调用方通过 trigger_texts 传入。
        """
        active_node_ids = []

        if trigger_texts:
            all_nodes = list(self.engine.nx_graph.nodes(data='data'))
            for _, node in all_nodes:
                if node and any(t in node.content for t in trigger_texts):
                    active_node_ids.append(node.id)

        if not active_node_ids:
            # 降级：取最近的 episode 或 event 作为扩散源
            episodes = self.engine.find_nodes_by_type(NodeType.EPISODE)
            events = self.engine.find_nodes_by_type(NodeType.EVENT)
            fallback = sorted(episodes + events, key=lambda n: n.created_at, reverse=True)[:2]
            active_node_ids = [n.id for n in fallback]

        if not active_node_ids:
            return "无相关记忆记录。"

        relevant_nodes = self.retriever.spread_activation(
            start_node_ids=active_node_ids,
            max_depth=2,
            top_k=top_k
        )

        # 格式化为可注入提示词的文本
        lines = ["=== 相关联的记忆图谱切片 ==="]
        for node in relevant_nodes:
            edges = list(self.engine.nx_graph.out_edges(node.id, data=True))
            if edges:
                for src, tgt, data in edges[:3]:
                    target_node = self.engine.get_node(tgt)
                    if target_node:
                        lines.append(
                            f"[{node.type.upper()}] {node.content} "
                            f"--({data['relation']})--> "
                            f"[{target_node.type.upper()}] {target_node.content}"
                        )
            else:
                lines.append(f"[{node.type.upper()}] {node.content}")

        return "\n".join(lines)

    # ==================== 兼容性：保留旧接口 ====================

    def experience(self, event_description: str, context_hints: Dict[str, Any] = None) -> None:
        """
        兼容旧代码的接口。将调用转发到工作记忆的 log()。
        新代码应直接使用 log() 方法。
        """
        logger.debug("experience() 被调用（兼容模式），转发到 working_memory.append()")
        self.working_memory.append("observation", event_description)

