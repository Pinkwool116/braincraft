"""
Dream 反思模块 — 图谱后台维护

在独立异步任务中运行，不阻塞 Agent Loop。
使用 asyncio.Lock 保护所有写操作。
"""

import time
import json
import re
import logging
from typing import List, Dict, Tuple

from .graph_engine import GraphEngine
from .graph_types import Node
from .embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)


class GraphDream:
    """
    Dream 反思：定期在图谱上运行维护操作。

    流程：候选发现 → LLM 精炼 → 应用变更 → 归档清理
    """

    def __init__(
        self,
        engine: GraphEngine,
        embedding: EmbeddingProvider = None,
        llm=None,
        prompt_manager=None,
        config: Dict = None,
        prompt_logger=None
    ):
        self.engine = engine
        self.embedding = embedding
        self.llm = llm
        self.prompt_manager = prompt_manager
        self.config = config or {}
        self.prompt_logger = prompt_logger

    # ======== Phase 1: 候选发现 ========

    def find_exact_duplicates(self, edit_threshold: int = 5) -> List[Tuple[Node, Node]]:
        """
        精确去重：content 完全相同或编辑距离 <= threshold。
        仅比较同类型节点。跳过失效节点。
        """
        pairs = []
        valid = [n for n in self.engine.get_all_nodes()
                 if getattr(n, 'invalid_at', None) is None]

        for i, a in enumerate(valid):
            for b in valid[i+1:]:
                if a.type != b.type:
                    continue
                if a.content == b.content:
                    pairs.append((a, b))
                elif (edit_threshold > 0 and
                      self._edit_distance(a.content, b.content) <= edit_threshold):
                    pairs.append((a, b))
        return pairs

    async def find_semantic_duplicates(
        self, threshold: float = 0.9
    ) -> List[Tuple[Node, Node, float]]:
        """
        语义去重：embedding 余弦相似度 > threshold。
        """
        if not self.embedding or not self.embedding.enabled:
            return []

        valid = [n for n in self.engine.get_all_nodes()
                 if getattr(n, 'invalid_at', None) is None]
        await self.embedding.ensure_node_embeddings(valid)

        from .embedding_provider import cosine_similarity

        pairs = []
        for i, a in enumerate(valid):
            va = self.embedding.get_node_embedding(a.id)
            if not va:
                continue
            for b in valid[i+1:]:
                vb = self.embedding.get_node_embedding(b.id)
                if not vb:
                    continue
                sim = cosine_similarity(va, vb)
                if sim >= threshold:
                    pairs.append((a, b, sim))

        pairs.sort(key=lambda x: x[2], reverse=True)
        return pairs[:50]

    def find_cold_nodes(
        self, access_threshold: int = 0, age_game_days: float = 7
    ) -> List[Node]:
        """
        低频节点：access_count <= threshold 且创建超过 N 个游戏日。
        排除 community 和 pattern 类型（它们是长期价值节点）。
        """
        now = self.engine._game_day()
        cutoff = now - age_game_days
        return [
            n for n in self.engine.get_all_nodes()
            if (n.access_count <= access_threshold and
                n.created_at < cutoff and
                n.type not in ("community", "pattern"))
        ]

    def find_weak_edges(
        self, weight_threshold: float = 0.1, age_game_days: float = 3
    ) -> List[Tuple[str, str, str]]:
        """低权重且老旧的边。"""
        now = self.engine._game_day()
        cutoff = now - age_game_days
        weak = []
        for src, tgt, data in self.engine.nx_graph.edges(data=True):
            if data.get('invalid_at') is not None:
                continue
            if (data.get('weight', 1.0) < weight_threshold and
                    data.get('created_at', 0) < cutoff):
                weak.append((src, tgt, data.get('relation', '')))
        return weak

    # ======== Phase 2: LLM 精炼 ========

    async def refine_with_llm(
        self,
        exact_dupes: List[Tuple[Node, Node]],
        semantic_dupes: List[Tuple[Node, Node, float]],
        cold_nodes: List[Node],
        weak_edges: List[Tuple[str, str, str]]
    ) -> Dict:
        """将候选问题发送 LLM，返回 merge/summarize/prune 计划。"""
        if not self.llm or not self.prompt_manager:
            return {}

        sections = []

        if exact_dupes:
            lines = ["## 精确重复节点"]
            for a, b in exact_dupes[:10]:
                lines.append(f"- [{a.type}] {a.content} (id={a.id})")
                lines.append(f"  vs [{b.type}] {b.content} (id={b.id})")
            sections.append("\n".join(lines))

        if semantic_dupes:
            lines = ["## 语义相近节点"]
            for a, b, sim in semantic_dupes[:10]:
                lines.append(f"- [{a.type}] {a.content} (id={a.id})")
                lines.append(f"  vs [{b.type}] {b.content} (id={b.id}) sim={sim:.3f}")
            sections.append("\n".join(lines))

        if cold_nodes:
            lines = ["## 低频/长期未访问节点"]
            for n in cold_nodes[:10]:
                lines.append(
                    f"- [{n.type}] {n.content} (id={n.id}, access={n.access_count})"
                )
            sections.append("\n".join(lines))

        if weak_edges:
            lines = ["## 低权重/老旧边"]
            for src, tgt, rel in weak_edges[:10]:
                sn = self.engine.get_node(src)
                tn = self.engine.get_node(tgt)
                if sn and tn:
                    lines.append(
                        f"- [{sn.type}]{sn.content} --({rel})--> [{tn.type}]{tn.content}"
                    )
            sections.append("\n".join(lines))

        if not sections:
            return {}

        prompt = await self.prompt_manager.render(
            'memory/memory_dream.md',
            context={'CANDIDATES': "\n\n".join(sections)},
            strict=False
        )

        try:
            prompt_file = None
            if self.prompt_logger:
                prompt_file = self.prompt_logger.log_prompt(
                    prompt=prompt,
                    brain_layer="memory_graph",
                    prompt_type="dream_refine"
                )

            response = await self.llm.send_request(
                [{"role": "user", "content": prompt}]
            )

            if prompt_file and response:
                self.prompt_logger.update_response(prompt_file, response)

            match = re.search(r'\{.*\}', response, re.DOTALL | re.MULTILINE)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            logger.error(f"Dream LLM refinement failed: {e}")

        return {}

    # ======== Phase 3: 应用变更 ========

    def apply_refinement(self, plan: Dict):
        """将 LLM 精炼计划应用到图谱。"""

        # 合并节点对
        for merge in plan.get("merge_pairs", []):
            a_id = merge.get("node_a_id") or self._find_id(merge.get("node_a", ""))
            b_id = merge.get("node_b_id") or self._find_id(merge.get("node_b", ""))
            merged = merge.get("merged_content", "")

            if a_id and b_id and a_id != b_id:
                if merged:
                    keep = self.engine.get_node(a_id)
                    if keep:
                        keep.content = merged
                self.engine.merge_nodes(a_id, b_id)
                logger.info(f"Dream merged: {a_id} + {b_id}")

        # 归纳组
        for summ in plan.get("summarize_groups", []):
            contents = summ.get("node_contents", [])
            ids = [self._find_id(c) for c in contents]
            ids = [i for i in ids if i]
            pat = summ.get("new_pattern", {})

            if ids and pat.get("content"):
                p = self.engine.add_node(
                    pat.get("type", "pattern"),
                    pat["content"],
                    pat.get("metadata", {})
                )
                for nid in ids:
                    node = self.engine.get_node(nid)
                    if node:
                        node.summarized_to = p.id
                    self.engine.add_edge(
                        p.id, nid, relation="SUMMARIZED_FROM", weight=0.8
                    )
                logger.info(f"Dream summarized {len(ids)} nodes → pattern {p.id}")

        # 剪枝节点
        for c in plan.get("prune_nodes", []):
            nid = self._find_id(c) if isinstance(c, str) else c
            if nid and self.engine.nx_graph.has_node(nid):
                self.engine.remove_node_permanently(nid)
                logger.info(f"Dream pruned node: {c if isinstance(c, str) else nid}")

        # 剪枝边
        for e in plan.get("prune_edges", []):
            if isinstance(e, dict):
                src = self._find_id(e.get("source", ""))
                tgt = self._find_id(e.get("target", ""))
                if src and tgt:
                    self.engine.remove_edge_permanently(src, tgt)

    def _find_id(self, ref: str) -> str:
        """通过 content 或 ID 查找节点 ID。"""
        if not ref:
            return ""
        if self.engine.nx_graph.has_node(ref):
            return ref
        for nid, data in self.engine.nx_graph.nodes(data=True):
            if data['data'].content == ref:
                return nid
        return ""

    # ======== 归档清理 ========

    def archive_deprecated(self, age_game_days: float = 30) -> int:
        """永久删除 invalid_at 超过 N 个游戏日的失效节点（access_count=0）。"""
        now = self.engine._game_day()
        cutoff = now - age_game_days
        to_remove = []
        for nid, data in self.engine.nx_graph.nodes(data=True):
            node = data['data']
            if (getattr(node, 'invalid_at', None) is not None and
                    node.invalid_at < cutoff and
                    node.access_count == 0):
                to_remove.append(nid)

        for nid in to_remove:
            self.engine.remove_node_permanently(nid)

        if to_remove:
            logger.info(f"Archived {len(to_remove)} deprecated nodes")
        return len(to_remove)

    # ======== 工具方法 ========

    @staticmethod
    def _edit_distance(a: str, b: str) -> int:
        """Levenshtein 编辑距离。"""
        m, n = len(a), len(b)
        if m == 0:
            return n
        if n == 0:
            return m
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        for i in range(m + 1):
            dp[i][0] = i
        for j in range(n + 1):
            dp[0][j] = j
        for i in range(1, m + 1):
            for j in range(1, n + 1):
                cost = 0 if a[i-1] == b[j-1] else 1
                dp[i][j] = min(dp[i-1][j] + 1, dp[i][j-1] + 1, dp[i-1][j-1] + cost)
        return dp[m][n]
