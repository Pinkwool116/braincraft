"""
记忆路由器（MemoryRouter） - 大脑与记忆系统的统一接口

核心设计：积累 → 反思 → 沉淀
- 工作记忆（WorkingMemoryBuffer）：任务执行时的临时缓冲区，线性追加原始体验
- 长期记忆（GraphEngine）：经过反思蒸馏后的结构化图谱
- 唯一的转化通道：crystallize() 在任务边界点将工作记忆蒸馏为图谱节点和边

任务执行时往工作记忆"写日记"，任务结束后通过 LLM 反思把日记"蒸馏"成图谱。
"""

import asyncio
import logging
import json
import re
import os
import time
from typing import Dict, Any, List, Optional

from .graph_engine import GraphEngine
from .graph_retriever import GraphRetriever
from .working_memory import WorkingMemoryBuffer
from .graph_types import NodeType, EdgeRelation
from .embedding_provider import EmbeddingProvider
from prompts.prompt_logger import PromptLogger

logger = logging.getLogger(__name__)


class MemoryRouter:
    """
    大脑（Brain）与记忆系统的统一接口。
    管理工作记忆（短期）和图谱记忆（长期）两个层级。
    """

    def __init__(self, agent_name: str, enable_logging: bool = True,
                 embedding_config: Dict = None, llm=None,
                 game_time_provider=None, memory_config: Dict = None,
                 prompt_manager=None):
        self.agent_name = agent_name
        self._game_time_provider = game_time_provider
        self._cfg = memory_config or {}

        # 长期记忆：图谱
        self.engine = GraphEngine(agent_name, game_time_provider=game_time_provider)
        self.retriever = GraphRetriever(self.engine)

        # 语义向量化
        self.embedding = EmbeddingProvider(agent_name, embedding_config)

        # 工作记忆缓冲区
        consolidate_interval = self._cfg.get('consolidate_interval', 30)
        self.working_memory = WorkingMemoryBuffer(agent_name, consolidate_interval=consolidate_interval)

        # 记忆操作专用 LLM（压缩 + 反思蒸馏）
        self.llm = llm

        # 提示词管理器（统一加载方式）
        self.prompt_manager = prompt_manager

        # 动态获取 bots_dir
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        bots_dir = os.path.join(str(project_root), "bots")

        # 日志
        self.prompt_logger = PromptLogger(bots_dir, agent_name, enabled=enable_logging)

        # Dream 状态（Phase 3 使用，Phase 1 仅声明）
        self._dream_instance = None
        self._cluster_instance = None
        self.crystallize_count = 0
        self._write_lock = asyncio.Lock()

        logger.info(f"MemoryRouter 初始化完成 '{agent_name}'")

    def _game_day(self) -> float:
        """获取当前游戏天数（小数）。"""
        if self._game_time_provider:
            return self._game_time_provider()
        return time.time() / 86400

    # ==================== 工作记忆接口 ====================

    def begin_task(self, goal: str, environment_snapshot: str = "",
                   task_plan: List[str] = None, strategic_reasoning: str = ""):
        """
        任务开始时调用，初始化工作记忆会话。

        Args:
            goal: 任务目标描述
            environment_snapshot: 当前环境状态快照（位置、生物群系等）
            task_plan: 高层拆分的步骤列表
            strategic_reasoning: 高层的战略推理
        """
        self.working_memory.begin_task(goal, environment_snapshot, task_plan, strategic_reasoning)

    def log(self, entry_type: str, content: str, detail: str = None,
            game_state: Dict[str, Any] = None, metadata: Dict[str, Any] = None,
            preserve: bool = False, consolidate_weight: int = 1):
        """
        向工作记忆追加一条记录（替代旧的 experience() 方法）。

        在任务执行过程中调用，无需关心这条记录未来会变成什么图谱节点。

        Args:
            entry_type: "action" | "observation" | "failure" | "interaction" |
                        "discovery" | "reasoning" | "code_attempt"
            content: 发生了什么
            detail: 可选补充信息
            game_state: 可选的当前游戏状态快照
            metadata: 可选的结构化补充数据（如LLM推理、关键代码调用等）
            preserve: 若为True，该条目在滚动压缩时不会被压缩，原封保留
            consolidate_weight: 1=计入consolidate触发配额, 0=不计入(observation)
        """
        self.working_memory.append(entry_type, content, detail, game_state,
                                   metadata=metadata, preserve=preserve,
                                   consolidate_weight=consolidate_weight)

    def end_task(self, result: str, summary: str = ""):
        """
        任务结束时调用。result: "success" | "failure" | "abandoned"
        """
        self.working_memory.end_task(result, summary)

    @property
    def consolidate_count_since_crystallize(self) -> int:
        """自上次 crystallize 以来的 consolidate 次数（跨任务持久化）。"""
        return self.working_memory.consolidate_count_since_crystallize

    def should_consolidate(self) -> bool:
        """检查工作记忆是否需要滚动压缩。"""
        return self.working_memory.should_consolidate()

    async def consolidate(self) -> None:
        """
        滚动压缩：将当前摘要与新增原始条目一起输入 LLM，
        LLM 输出新的完整摘要全量替换旧摘要。
        已消费的原始条目从工作记忆中移除。
        """
        if not self.llm:
            logger.warning("未配置 memory LLM，跳过 consolidate")
            return
        if not self.prompt_manager:
            logger.warning("缺少 PromptManager，跳过 consolidate")
            return

        new_entries, current_summary = self.working_memory.get_entries_for_consolidation()
        if not new_entries:
            return

        # 格式化新增条目
        entry_lines = []
        for entry in new_entries:
            line = self._format_entry_for_prompt(entry)
            entry_lines.append(line)

        # 构建压缩提示词
        goal = self.working_memory.context.get("goal", "未知")
        strategic = self.working_memory.context.get("strategic_reasoning", "")
        environment = self.working_memory.context.get("environment", "")

        prompt = await self.prompt_manager.render(
            'memory/working_memory_consolidation.md',
            context={
                'GOAL': goal,
                'STRATEGIC_REASONING': strategic,
                'ENVIRONMENT': environment,
                'CURRENT_SUMMARY': current_summary if current_summary else "（尚无摘要，这是第一次压缩）",
                'NEW_ENTRIES': "\n".join(entry_lines),
            },
            strict=False
        )

        prompt_file = self.prompt_logger.log_prompt(
            prompt=prompt,
            brain_layer="memory_graph",
            prompt_type="consolidate"
        )

        try:
            response = await self.llm.send_request(
                [{"role": "user", "content": prompt}]
            )
            self.prompt_logger.update_response(prompt_file, response)

            new_summary = response.strip()
            if new_summary:
                self.working_memory.update_summary(new_summary, consumed_entries=new_entries)
                self.working_memory.consolidate_count_since_crystallize += 1
                logger.info(f"工作记忆滚动压缩完成：{len(new_entries)} 条新条目已融入摘要")
            else:
                logger.warning("consolidate: LLM 返回空摘要")

        except Exception as e:
            logger.error(f"工作记忆压缩失败: {e}", exc_info=True)

    @staticmethod
    def _format_entry_for_prompt(entry: Dict[str, Any]) -> str:
        """将一条工作记忆条目格式化为提示词中的文本行。"""
        tag = entry.get("type", "unknown").upper()
        content = entry.get("content", "")
        preserved_tag = "[重要/PRESERVED] " if entry.get("preserve") else ""
        line = f"{preserved_tag}[{tag}] {content}"
        if entry.get("detail"):
            line += f"\n  详情: {entry['detail']}"
        # 包含 metadata 中的结构化信息
        meta = entry.get("metadata")
        if meta:
            meta_parts = [f"{k}: {v}" for k, v in meta.items()
                          if v and k not in ('snapshot',)]
            if meta_parts:
                line += f"\n  附加: {'; '.join(str(p) for p in meta_parts)}"
        snapshot_text = WorkingMemoryBuffer._format_snapshot(entry.get("snapshot"))
        if snapshot_text:
            line += f"\n  {snapshot_text.strip(' |')}"
        return line

    # ==================== 反思（工作记忆 → 长期记忆） ====================

    async def crystallize(self) -> None:
        """
        反思过程：将工作记忆蒸馏为长期记忆图谱节点和边。
        在任务边界点（结束/放弃）调用。使用写锁保护图谱修改。
        """
        if not self.llm:
            logger.warning("未配置 memory LLM，跳过 crystallize")
            raise NotImplementedError("Memory LLM is required for crystallize")
        if not self.working_memory.has_content:
            logger.debug("工作记忆为空，跳过 crystallize")
            return

        if not self.prompt_manager:
            logger.error("缺少 PromptManager，跳过 crystallize")
            raise NotImplementedError("PromptManager is required for crystallize")

        async with self._write_lock:
            buffer_text = self.working_memory.get_buffer_text()

            existing_context = await self._get_existing_context_for_reflection()

            prompt = await self.prompt_manager.render(
                'memory/memory_graph_extraction.md',
                context={
                    'BUFFER_TEXT': buffer_text,
                    'EXISTING_CONTEXT': existing_context,
                },
                strict=False
            )

            prompt_file = self.prompt_logger.log_prompt(
                prompt=prompt,
                brain_layer="memory_graph",
                prompt_type="crystallize"
            )

            try:
                response = await self.llm.send_request(
                    [{"role": "user", "content": prompt}]
                )
                self.prompt_logger.update_response(prompt_file, response)

                match = re.search(r'\{.*\}', response, re.DOTALL | re.MULTILINE)
                if match:
                    data = json.loads(match.group(0))
                    new_node_ids = self._integrate_llm_extraction(data)
                    logger.info("crystallize 完成：工作记忆已蒸馏为图谱节点")

                    # 异步生成新节点的 embedding
                    if new_node_ids and self.embedding.enabled:
                        new_nodes = [self.engine.get_node(nid) for nid in new_node_ids if self.engine.get_node(nid)]
                        if new_nodes:
                            await self.embedding.ensure_node_embeddings(new_nodes)
                            logger.debug(f"已为 {len(new_nodes)} 个新节点生成 embedding")
                else:
                    logger.warning("crystallize: LLM 返回中未找到 JSON")

            except Exception as e:
                logger.error(f"crystallize 失败: {e}", exc_info=True)
                return  # 失败时不清空工作记忆，下次可以重试

            # 生成骨架摘要（仅供 Agent 上下文，不参与后续 consolidate/crystallize）
            new_nodes = new_node_ids if 'new_node_ids' in locals() else []
            skeleton = self._build_skeleton_summary(new_nodes)
            self.working_memory.skeleton_summary = skeleton

            # 清空工作记忆（保留摘要和骨架），重置计数器
            self.working_memory.clear()
            self.working_memory.consolidate_count_since_crystallize = 0
            self.crystallize_count += 1

    async def _get_existing_context_for_reflection(self) -> str:
        """
        语义搜索 + 扩散激活获取已有图谱中的相关上下文。

        流程：
        1. 用工作记忆摘要文本做 embedding 语义匹配种子节点
        2. 从种子节点做 1 跳扩散激活获取关联邻居
        3. 将节点（含 ID）及边格式化为 LLM 可读文本
        """
        if not self.working_memory.has_content:
            return "暂无已有记忆。"

        buffer_text = self.working_memory.get_buffer_text()
        all_nodes = self.engine.get_all_nodes()
        if not all_nodes:
            return "暂无已有记忆。"

        seed_ids = set()

        # 1. 语义匹配种子节点
        if self.embedding.enabled:
            try:
                results = await self.embedding.find_similar_nodes(
                    query_texts=[buffer_text[:2000]],
                    candidate_nodes=all_nodes,
                    top_k=self._cfg.get("crystallize_context_top_k", 10),
                    threshold=self._cfg.get("embedding_similarity_threshold", 0.3)
                )
                seed_ids.update(node.id for node, _ in results)
            except Exception:
                pass

        # 2. 降级：用任务目标做子串匹配
        if not seed_ids:
            goal = self.working_memory.context.get("goal", "")
            for node in all_nodes:
                if goal and len(goal) > 2 and goal.lower() in node.content.lower():
                    seed_ids.add(node.id)

        # 仍不够则取最近的事件
        if not seed_ids:
            events = [n for n in all_nodes if n.type == NodeType.EVENT]
            fallback = sorted(events, key=lambda n: n.created_at, reverse=True)[:3]
            seed_ids = {n.id for n in fallback}

        if not seed_ids:
            return "暂无已有记忆。"

        # 3. 从种子做 1 跳扩散激活
        relevant_node_ids = set(seed_ids)
        for seed_id in seed_ids:
            for nbr in list(self.engine.nx_graph.successors(seed_id)):
                nbr_node = self.engine.get_node(nbr)
                if nbr_node and getattr(nbr_node, 'invalid_at', None) is None:
                    relevant_node_ids.add(nbr)
            for pred in list(self.engine.nx_graph.predecessors(seed_id)):
                pred_node = self.engine.get_node(pred)
                if pred_node and getattr(pred_node, 'invalid_at', None) is None:
                    relevant_node_ids.add(pred)

        # 4. 格式化：节点 + 它们之间的边
        relevant_nodes = [self.engine.get_node(nid) for nid in relevant_node_ids]
        relevant_nodes = [n for n in relevant_nodes if n is not None]

        lines = []
        for node in relevant_nodes:
            meta_str = ""
            if node.metadata:
                flat = {k: v for k, v in node.metadata.items() if v and k != 'embedding'}
                if flat:
                    meta_str = f" (metadata: {json.dumps(flat, ensure_ascii=False)})"
            lines.append(f"  [ID={node.id}] [{node.type}] {node.content}{meta_str}")

            # 显示该节点与其他相关节点之间的边
            for src, tgt, edata in self.engine.nx_graph.out_edges(node.id, data=True):
                if edata.get('invalid_at') is not None:
                    continue
                if tgt not in relevant_node_ids:
                    continue
                tgt_node = self.engine.get_node(tgt)
                if tgt_node and getattr(tgt_node, 'invalid_at', None) is None:
                    lines.append(f"      --({edata['relation']})--> [ID={tgt_node.id}] [{tgt_node.type}] {tgt_node.content}")

        return "\n".join(lines) if lines else "暂无已有记忆。"

    # ==================== 图谱整合 ====================

    def _integrate_llm_extraction(self, graph_data: dict) -> List[str]:
        """
        将 LLM 提取的结构化 JSON 合并到图谱中。返回新创建的节点 ID 列表。

        支持 LLM 输出中的新字段：
        - nodes: 节点列表（可含 id 复用已有节点，可含 invalid_at）
        - edges: 边列表（source/target 可为已有节点 ID 或 content）
        - deprecations: 标记失效的节点/边
        - summarizations: 归纳多个节点为 pattern
        """
        content_to_id = {}
        new_node_ids = []

        # === 合并节点 ===
        for n in graph_data.get("nodes", []):
            content = n.get("content")
            n_type = n.get("type", NodeType.EVENT)
            n_id = n.get("id")  # LLM 可指定已有节点 ID
            invalid_at = n.get("invalid_at")

            if not content:
                continue

            # LLM 给出了已有节点 ID → 直接复用
            if n_id and self.engine.nx_graph.has_node(n_id):
                target_node = self.engine.get_node(n_id)
                if target_node and getattr(target_node, 'invalid_at', None) is None:
                    content_to_id[content] = n_id
                    target_node.access_count += 1
                    self._merge_metadata(target_node, n.get("metadata", {}))
                    continue

            # 按 content + type 去重
            existing = [x for x in self.engine.find_nodes_by_type(n_type)
                        if x.content == content and getattr(x, 'invalid_at', None) is None]
            if existing:
                target_node = existing[0]
                content_to_id[content] = target_node.id
                target_node.access_count += 1
                self._merge_metadata(target_node, n.get("metadata", {}))
            else:
                metadata = n.get("metadata", {})
                new_node = self.engine.add_node(n_type, content, metadata)
                if invalid_at:
                    new_node.invalid_at = invalid_at
                content_to_id[content] = new_node.id
                new_node_ids.append(new_node.id)

        # === 链接边 ===
        for e in graph_data.get("edges", []):
            src_ref = e.get("source")
            tgt_ref = e.get("target")
            relation = e.get("relation", EdgeRelation.RELATED_TO)
            weight = e.get("weight", 1.0)
            invalid_at = e.get("invalid_at")

            # 优先当节点 ID 解析，失败则查 content_to_id
            src_id = src_ref if (src_ref and self.engine.nx_graph.has_node(src_ref)) else content_to_id.get(src_ref)
            tgt_id = tgt_ref if (tgt_ref and self.engine.nx_graph.has_node(tgt_ref)) else content_to_id.get(tgt_ref)

            if src_id and tgt_id:
                self.engine.add_edge(src_id, tgt_id, relation=relation, weight=weight)
                if invalid_at:
                    self.engine.nx_graph.edges[src_id, tgt_id]['invalid_at'] = invalid_at

        # === 处理 deprecations ===
        for dep in graph_data.get("deprecations", []):
            node_content = dep.get("node_content", "")
            node_id = dep.get("node_id")
            reason = dep.get("reason", "")

            target_id = node_id or self._find_node_by_content(node_content)
            if target_id:
                self.engine.mark_node_deprecated(target_id)
                logger.info(f"标记节点失效: {node_content or node_id} (原因: {reason})")

            # 边失效
            edge_spec = dep.get("edge")
            if edge_spec:
                src = edge_spec.get("source_id") or self._find_node_by_content(edge_spec.get("source", ""))
                tgt = edge_spec.get("target_id") or self._find_node_by_content(edge_spec.get("target", ""))
                if src and tgt:
                    self.engine.mark_edge_deprecated(src, tgt)
                    logger.info(f"标记边失效: {src} -> {tgt} (原因: {reason})")

        # === 处理 summarizations ===
        for summ in graph_data.get("summarizations", []):
            src_refs = summ.get("source_node_ids", []) or summ.get("source_node_contents", [])
            target_data = summ.get("target", {})
            if not src_refs or not target_data:
                continue

            src_ids = []
            for ref in src_refs:
                nid = ref if self.engine.nx_graph.has_node(ref) else self._find_node_by_content(ref)
                if nid:
                    src_ids.append(nid)

            if not src_ids:
                continue

            summ_type = target_data.get("type", NodeType.PATTERN)
            summ_content = target_data.get("content", "")
            if not summ_content:
                continue

            summ_node = self.engine.add_node(summ_type, summ_content, target_data.get("metadata", {}))
            new_node_ids.append(summ_node.id)

            for src_id in src_ids:
                node = self.engine.get_node(src_id)
                if node:
                    node.summarized_to = summ_node.id
                self.engine.add_edge(summ_node.id, src_id, relation="SUMMARIZED_FROM", weight=0.8)

        self.engine.save()
        return new_node_ids

    def _find_node_by_content(self, content: str) -> Optional[str]:
        """通过 content 精确匹配查找节点 ID。"""
        if not content:
            return None
        for nid, data in self.engine.nx_graph.nodes(data=True):
            if data['data'].content == content:
                return nid
        return None

    # ==================== 检索（长期记忆 → 提示词注入） ====================

    async def retrieve_context_async(self, trigger_texts: List[str] = None, top_k: int = 8) -> str:
        """
        检索相关记忆上下文，格式化为可注入提示词的文本。

        种子选择：语义匹配 + 子串匹联合并后扩散激活。
        """
        all_nodes = self.engine.get_all_nodes()
        seed_ids = set()

        # 语义匹配 + 子串匹配并行
        if trigger_texts and all_nodes:
            if self.embedding.enabled:
                results = await self.embedding.find_similar_nodes(
                    query_texts=trigger_texts,
                    candidate_nodes=all_nodes,
                    top_k=top_k,
                    threshold=self._cfg.get("embedding_similarity_threshold", 0.3)
                )
                seed_ids.update(node.id for node, _ in results)

            # 子串匹配（与语义结果合并，覆盖语义遗漏的精确匹配）
            for node in all_nodes:
                if any(t.lower() in node.content.lower() for t in trigger_texts if len(t) > 2):
                    seed_ids.add(node.id)

        if not seed_ids:
            events = [n for n in all_nodes if n.type == NodeType.EVENT]
            fallback = sorted(events, key=lambda n: n.created_at, reverse=True)[:3]
            seed_ids = {n.id for n in fallback}

        if not seed_ids:
            return "无相关记忆记录。"

        relevant_nodes = self.retriever.spread_activation(
            start_node_ids=list(seed_ids),
            max_depth=self._cfg.get("retrieval_max_depth", 2),
            top_k=top_k
        )

        lines = ["=== 相关联的记忆图谱切片 ==="]
        for node in relevant_nodes:
            edges = list(self.engine.nx_graph.out_edges(node.id, data=True))
            valid_edges = [(s, t, d) for s, t, d in edges if d.get('invalid_at') is None]
            if valid_edges:
                for src, tgt, data in valid_edges[:3]:
                    target_node = self.engine.get_node(tgt)
                    if target_node and getattr(target_node, 'invalid_at', None) is None:
                        lines.append(
                            f"[{node.type.upper()}] {node.content} "
                            f"--({data['relation']})--> "
                            f"[{target_node.type.upper()}] {target_node.content}"
                        )
            else:
                lines.append(f"[{node.type.upper()}] {node.content}")

        return "\n".join(lines)

    # ==================== Dream 反思循环（Phase 3 使用） ====================

    async def dream_if_needed(self, config: Dict = None) -> bool:
        """
        后台调用。满足条件则异步执行 Dream，否则跳过。

        由 BrainCoordinator 的 _run_dream_monitor 协程定期调用。
        """
        cfg = config or self._cfg
        interval = cfg.get("dream_interval", 10)
        min_nodes = cfg.get("dream_min_nodes", 30)

        if self.crystallize_count < interval:
            return False
        if self.engine.nx_graph.number_of_nodes() < min_nodes:
            self.crystallize_count = 0
            return False

        asyncio.create_task(self._run_dream(cfg))
        self.crystallize_count = 0
        return True

    async def _run_dream(self, config: Dict):
        """Dream 完整流程：社区聚类 + 去重反思 + 归档。"""
        from .graph_dream import GraphDream
        from .graph_cluster import GraphCluster

        cfg = {**self._cfg, **(config or {})}  # 合并，调用方参数优先

        async with self._write_lock:
            logger.info("=== Dream cycle started ===")

            if self._dream_instance is None:
                self._dream_instance = GraphDream(
                    engine=self.engine, embedding=self.embedding,
                    llm=self.llm, prompt_manager=self.prompt_manager,
                    config=cfg, prompt_logger=self.prompt_logger)
            if self._cluster_instance is None:
                self._cluster_instance = GraphCluster(
                    engine=self.engine, llm=self.llm,
                    prompt_manager=self.prompt_manager,
                    prompt_logger=self.prompt_logger)

            community_count = 0
            dupes_found = 0
            archived = 0

            # 1. 社区聚类
            communities = self._cluster_instance.find_communities(
                min_size=cfg.get("community_min_size", 3))
            if communities:
                existing = self.engine.find_nodes_by_type("community")
                new_comm = await self._cluster_instance.generate_community_nodes(
                    communities, existing)
                if new_comm:
                    await self.embedding.ensure_node_embeddings(new_comm)
                    community_count = len(new_comm)
                    logger.info(f"Created {community_count} community nodes")

            # 2. 候选发现
            dream = self._dream_instance
            exact = dream.find_exact_duplicates(
                cfg.get("dedup_edit_distance_threshold", 5))
            sem = await dream.find_semantic_duplicates(
                cfg.get("dedup_similarity_threshold", 0.9))
            cold = dream.find_cold_nodes(
                cfg.get("prune_access_threshold", 0),
                cfg.get("prune_age_days", 7))
            weak = dream.find_weak_edges(
                cfg.get("weak_edge_weight_threshold", 0.1),
                cfg.get("weak_edge_age_days", 3))
            dupes_found = len(exact) + len(sem)

            # 3. LLM 精炼
            if any([exact, sem, cold, weak]):
                plan = await dream.refine_with_llm(exact, sem, cold, weak)
                if plan:
                    dream.apply_refinement(plan)
                    logger.info(
                        f"Dream refinement applied: "
                        f"merges={len(plan.get('merge_pairs', []))}, "
                        f"summaries={len(plan.get('summarize_groups', []))}, "
                        f"prune_nodes={len(plan.get('prune_nodes', []))}"
                    )

            # 4. 归档
            archived = dream.archive_deprecated(
                cfg.get("archive_age_days", 30))

            # 5. Dream 摘要 thought
            summary = (
                f"Dream反思完成：聚类={community_count}社区，"
                f"重复={dupes_found}对，"
                f"剪枝候选={len(cold)}节点/{len(weak)}边，"
                f"归档={archived}"
            )
            self.engine.add_node("thought", summary, {
                "trigger": "dream_cycle",
                "community_count": community_count,
                "duplicates_found": dupes_found,
                "archived": archived,
            })

        logger.info("=== Dream cycle completed ===")

    # ==================== 骨架摘要 ====================

    def _build_skeleton_summary(self, new_node_ids: List[str]) -> str:
        """从新结晶的节点生成骨架摘要，仅用于 Agent 上下文。"""
        if not new_node_ids:
            return ""
        new_nodes = [self.engine.get_node(nid) for nid in new_node_ids if self.engine.get_node(nid)]
        if not new_nodes:
            return ""
        events = [n for n in new_nodes if n.type == NodeType.EVENT]
        if not events:
            return ""
        event_names = [e.content for e in events[:5]]
        return "已结晶的关键经历：" + " → ".join(event_names)

    @staticmethod
    def _merge_metadata(node, new_metadata: dict):
        """合并 metadata，保护坐标字段不被 LLM 覆盖。"""
        if not new_metadata:
            return
        protected_keys = {'coordinates', 'position'}
        for key in protected_keys:
            new_metadata.pop(key, None)
        if hasattr(node, 'metadata') and node.metadata is not None:
            node.metadata.update(new_metadata)

    # ==================== 兼容性：保留旧接口 ====================

    def experience(self, event_description: str, context_hints: Dict[str, Any] = None) -> None:
        """
        兼容旧代码的接口。将调用转发到工作记忆的 log()。
        新代码应直接使用 log() 方法。
        """
        logger.debug("experience() 被调用（兼容模式），转发到 working_memory.append()")
        self.working_memory.append("observation", event_description)
