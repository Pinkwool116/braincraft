"""
图检索器 - 扩散激活与记忆上下文选择

实现了扩散激活（Spreading Activation）算法，用于在给定一组焦点节点
（如触发器、当前位置、当前任务）的基础上深挖和寻找上下文相关的记忆。
"""

import time
import logging
from typing import List, Dict, Optional

import networkx as nx

from .graph_engine import GraphEngine
from .graph_types import Node

logger = logging.getLogger(__name__)

class GraphRetriever:
    """
    处理图遍历并进行相关度评分，以检索记忆上下文。
    """
    def __init__(self, engine: GraphEngine):
        self.engine = engine

    def _apply_decay(self, node: Node) -> float:
        """
        计算考虑了随时间衰减的记忆重要性。

        基础值 + 近期访问加成 + 访问频次加成。
        """
        base = 1.0
        recency_bonus = 0.5 if (time.time() - node.last_accessed) < 3600 else 0.0
        frequency_bonus = min(node.access_count * 0.1, 1.0)
        return base + recency_bonus + frequency_bonus

    def spread_activation(self, start_node_ids: List[str], max_depth: int = 3, top_k: int = 30) -> List[Node]:
        """
        从 start_node_ids 起始点执行扩散激活算法。

        跳过失效节点和失效边，使用边的真实权重作为衰减系数。

        参数:
            start_node_ids: 当前上下文的焦点节点ID列表。
            max_depth: 遍历边的最大深度。
            top_k: 返回相关性最高的节点数量。
        """
        activation_scores: Dict[str, float] = {}

        # 初始化起点节点
        q = []  # (节点ID, 当前能量, 当前深度)
        for nid in start_node_ids:
            if self.engine.nx_graph.has_node(nid):
                node = self.engine.nx_graph.nodes[nid]['data']
                if getattr(node, 'invalid_at', None) is not None:
                    continue
                q.append((nid, 10.0, 0))
                activation_scores[nid] = 10.0

        # 遍历图 (扩散，类似于广度优先搜索BFS)
        while q:
            current_id, energy, depth = q.pop(0)

            if depth >= max_depth:
                continue

            # 收集当前节点的邻居（双向），同时过滤失效
            raw_neighbors = (
                list(self.engine.nx_graph.successors(current_id)) +
                list(self.engine.nx_graph.predecessors(current_id))
            )
            neighbors = []
            for nbr_id in set(raw_neighbors):
                # 跳过失效的邻居节点
                nbr_node = self.engine.get_node(nbr_id)
                if nbr_node and getattr(nbr_node, 'invalid_at', None) is not None:
                    continue

                # 检查边是否失效
                edge_data = self.engine.nx_graph.get_edge_data(current_id, nbr_id)
                if not edge_data:
                    edge_data = self.engine.nx_graph.get_edge_data(nbr_id, current_id)
                if edge_data and edge_data.get('invalid_at') is not None:
                    continue

                neighbors.append(nbr_id)

            for nbr_id in neighbors:
                # 读取边的真实权重作为衰减系数（替换硬编码 0.5）
                edge_data = self.engine.nx_graph.get_edge_data(current_id, nbr_id)
                if not edge_data:
                    edge_data = self.engine.nx_graph.get_edge_data(nbr_id, current_id)
                edge_weight = edge_data.get('weight', 0.5) if edge_data else 0.5

                transferred_energy = energy * edge_weight

                if nbr_id not in activation_scores:
                    activation_scores[nbr_id] = 0.0
                activation_scores[nbr_id] += transferred_energy

                if transferred_energy > 0.1:
                    q.append((nbr_id, transferred_energy, depth + 1))

        # 结合节点自身的遗忘衰减/重要性权重
        final_scores = []
        for nid, score in activation_scores.items():
            node = self.engine.get_node(nid)
            if node:
                intrinsic_value = self._apply_decay(node)
                final_scores.append((node, score * intrinsic_value))

        # 排序并返回前 top_k 个节点
        final_scores.sort(key=lambda x: x[1], reverse=True)

        result_nodes = []
        for node, _ in final_scores[:top_k]:
            node.access_count += 1
            node.last_accessed = time.time()
            result_nodes.append(node)

        self.engine.save()
        return result_nodes

    # ==================== 路径查找 ====================

    def find_paths(
        self,
        entity_a: str,
        entity_b: str,
        max_length: int = 4,
        top_k: int = 3
    ) -> List[Dict]:
        """
        在记忆图谱中查找两个实体之间的最短路径。

        使用 NetworkX bidirectional_shortest_path，跳过失效节点和边。

        Args:
            entity_a: 实体 A 的描述文本（子串匹配节点 content）
            entity_b: 实体 B 的描述文本
            max_length: 路径的最大跳数
            top_k: 最多返回多少条路径

        Returns:
            [{"path_nodes": [Node, ...], "edge_relations": ["REL_A", ...],
              "length": 2, "description": "A --LOCATED_AT--> place --PART_OF--> B"}]
        """
        nodes_a = self._match_entity(entity_a)
        nodes_b = self._match_entity(entity_b)

        if not nodes_a or not nodes_b:
            return []

        results = []
        for a_id in nodes_a[:3]:
            for b_id in nodes_b[:3]:
                if a_id == b_id:
                    continue
                try:
                    path = nx.bidirectional_shortest_path(
                        self.engine.nx_graph, source=a_id, target=b_id
                    )
                    if len(path) > max_length + 1:
                        continue

                    edge_relations = []
                    for i in range(len(path) - 1):
                        edge_data = self.engine.nx_graph.get_edge_data(path[i], path[i+1])
                        if edge_data and edge_data.get('invalid_at') is None:
                            edge_relations.append(edge_data['relation'])
                        else:
                            rev = self.engine.nx_graph.get_edge_data(path[i+1], path[i])
                            edge_relations.append(f"<-{rev['relation']}" if rev else "RELATED_TO")

                    path_nodes = [self.engine.get_node(nid) for nid in path]

                    desc_parts = []
                    for i, node in enumerate(path_nodes):
                        desc_parts.append(f"[{node.type}]{node.content}")
                        if i < len(edge_relations):
                            desc_parts.append(f"--({edge_relations[i]})-->")

                    results.append({
                        "path_nodes": path_nodes,
                        "edge_relations": edge_relations,
                        "length": len(path) - 1,
                        "description": " ".join(desc_parts)
                    })
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue

        results.sort(key=lambda r: r["length"])
        return results[:top_k]

    def _match_entity(self, entity_text: str) -> List[str]:
        """
        通过子串匹配查找实体对应的节点 ID 列表。
        优先精确 content 匹配，其次子串匹配。跳过失效节点。
        """
        if not entity_text:
            return []
        exact = []
        substring = []
        for nid, data in self.engine.nx_graph.nodes(data=True):
            node = data['data']
            if getattr(node, 'invalid_at', None) is not None:
                continue
            if node.content == entity_text:
                exact.append(nid)
            elif entity_text.lower() in node.content.lower():
                substring.append(nid)
        return exact + substring
