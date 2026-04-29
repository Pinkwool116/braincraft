"""
图聚类模块 — 社区发现与高层抽象节点生成

使用 Louvain 算法发现紧密子图，并由 LLM 为每个社区生成摘要描述。
"""

import logging
from typing import List, Optional
import networkx as nx
from networkx.algorithms.community import louvain_communities

from .graph_engine import GraphEngine
from .graph_types import Node

logger = logging.getLogger(__name__)


class GraphCluster:
    """社区聚类：发现紧密子图并生成 Community Node。"""

    def __init__(self, engine: GraphEngine, llm=None, prompt_manager=None, prompt_logger=None):
        self.engine = engine
        self.llm = llm
        self.prompt_manager = prompt_manager
        self.prompt_logger = prompt_logger

    def find_communities(self, min_size: int = 3) -> List[List[str]]:
        """
        运行 Louvain 社区发现算法，返回每个社区的节点 ID 列表。

        只返回节点数 >= min_size 的社区。
        """
        # 构建无向加权图（忽略方向，只保留有效节点和边）
        G = nx.Graph()
        for nid, data in self.engine.nx_graph.nodes(data=True):
            node = data['data']
            if getattr(node, 'invalid_at', None) is not None:
                continue
            G.add_node(nid)

        for src, tgt, data in self.engine.nx_graph.edges(data=True):
            if data.get('invalid_at') is not None:
                continue
            if not G.has_node(src) or not G.has_node(tgt):
                continue
            w = data.get('weight', 1.0)
            if G.has_edge(src, tgt):
                G[src][tgt]['weight'] = G[src][tgt].get('weight', 0) + w
            else:
                G.add_edge(src, tgt, weight=w)

        if G.number_of_nodes() < min_size:
            return []

        try:
            communities = louvain_communities(G, weight='weight', seed=42)
        except Exception as e:
            logger.warning(f"Louvain clustering failed: {e}")
            return []

        result = [list(c) for c in communities if len(c) >= min_size]
        logger.info(f"Found {len(result)} communities (min_size={min_size})")
        return result

    async def generate_community_nodes(
        self,
        communities: List[List[str]],
        existing_community_nodes: List[Node]
    ) -> List[Node]:
        """
        为每个社区调用 LLM 生成 Community Node。

        Args:
            communities: 每个社区包含的节点 ID 列表
            existing_community_nodes: 已有的 community 节点（用于去重）

        Returns:
            新创建的 Community Node 列表
        """
        if not self.llm or not self.prompt_manager:
            logger.warning("No LLM or prompt manager for community clustering")
            return []

        existing_summaries = {n.content for n in existing_community_nodes}
        existing_text = "\n".join(f"- {s}" for s in existing_summaries) if existing_summaries else "暂无已有社区"
        new_nodes = []

        for comm_ids in communities:
            info = self._describe_community(comm_ids)
            if not info:
                continue

            prompt = await self.prompt_manager.render(
                'memory/community_clustering.md',
                context={
                    'COMMUNITY_NODES': info,
                    'EXISTING_COMMUNITIES': existing_text,
                },
                strict=False
            )

            try:
                prompt_file = None
                if self.prompt_logger:
                    prompt_file = self.prompt_logger.log_prompt(
                        prompt=prompt,
                        brain_layer="memory_graph",
                        prompt_type="community_cluster"
                    )

                response = await self.llm.send_request(
                    [{"role": "user", "content": prompt}]
                )
                response = response.strip()

                if prompt_file and response:
                    self.prompt_logger.update_response(prompt_file, response)

                # 解析: 社区名称 | 社区摘要 | ID1, ID2, ID3
                parts = response.split("|")
                if len(parts) >= 2:
                    name = parts[0].strip()
                    summary = parts[1].strip()
                    rep_ids = []
                    if len(parts) >= 3:
                        rep_ids = [rid.strip() for rid in parts[2].split(",")]

                    content = f"{name}：{summary}"
                    if content in existing_summaries:
                        continue

                    node = self.engine.add_node("community", content, {
                        "member_count": len(comm_ids),
                        "representative_ids": rep_ids,
                        "name": name,
                    })
                    # 用 CONTAINS 边连接社区节点与代表节点
                    for rid in rep_ids[:5]:
                        if self.engine.nx_graph.has_node(rid):
                            self.engine.add_edge(
                                node.id, rid, relation="CONTAINS", weight=0.7
                            )

                    new_nodes.append(node)
                    existing_summaries.add(content)

            except Exception as e:
                logger.error(f"Failed to generate community node: {e}")

        return new_nodes

    def _describe_community(self, node_ids: List[str]) -> str:
        """将社区内的节点和边格式化为 LLM 可读文本。"""
        lines = []
        for nid in node_ids:
            node = self.engine.get_node(nid)
            if node:
                lines.append(f"  [{node.type}] {node.content}")
                if node.metadata:
                    flat = {k: v for k, v in node.metadata.items()
                            if v and k != 'embedding'}
                    if flat:
                        lines.append(f"    metadata: {flat}")

        # 社区内部边
        for i, a in enumerate(node_ids):
            for b in node_ids[i+1:]:
                if self.engine.nx_graph.has_edge(a, b):
                    edata = self.engine.nx_graph.get_edge_data(a, b)
                    if edata.get('invalid_at') is None:
                        a_node = self.engine.get_node(a)
                        b_node = self.engine.get_node(b)
                        lines.append(
                            f"  边: [{a_node.type}]{a_node.content} "
                            f"--({edata['relation']})--> [{b_node.type}]{b_node.content}"
                        )

        return "\n".join(lines) if lines else ""
