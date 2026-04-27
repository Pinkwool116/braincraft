"""
图引擎 - 记忆管理与 NetworkX 封装

维护一个内存中的 NetworkX 有向图 (DiGraph)，处理节点/边的添加和删除。
作为记忆图配置的中心和唯一事实来源。
"""

import time
import networkx as nx
import logging
from typing import List, Dict, Any, Optional

from .graph_types import Node, Edge
from .graph_store import GraphStore

logger = logging.getLogger(__name__)

class GraphEngine:
    def __init__(self, agent_name: str, game_time_provider=None):
        self.agent_name = agent_name
        self.store = GraphStore(agent_name)
        self.nx_graph = nx.DiGraph()
        self._game_time_provider = game_time_provider  # callable -> float (游戏天数)

        self._initialize_from_store()

    def _game_day(self) -> float:
        """获取当前游戏天数（小数）。降级时使用现实时间。"""
        if self._game_time_provider:
            return self._game_time_provider()
        return time.time() / 86400

    def _initialize_from_store(self):
        """从存储中加载节点和边到 NetworkX 图中。"""
        nodes, edges = self.store.load_graph()

        for n_id, node in nodes.items():
            self.nx_graph.add_node(n_id, data=node)

        for edge in edges:
            if self.nx_graph.has_node(edge.source) and self.nx_graph.has_node(edge.target):
                self.nx_graph.add_edge(
                    edge.source,
                    edge.target,
                    relation=edge.relation,
                    weight=edge.weight,
                    metadata=edge.metadata,
                    created_at=getattr(edge, 'created_at', 0),
                    invalid_at=getattr(edge, 'invalid_at', None),
                )
        logger.info(f"Initialized GraphEngine with {self.nx_graph.number_of_nodes()} nodes and {self.nx_graph.number_of_edges()} edges.")

    def save(self):
        """将当前图状态分发给 GraphStore 进行持久化保存。"""
        nodes_dict: Dict[str, Node] = {}
        for n_id, data in self.nx_graph.nodes(data=True):
            nodes_dict[n_id] = data['data']

        edges_list: List[Edge] = []
        for src, tgt, data in self.nx_graph.edges(data=True):
            edges_list.append(Edge(
                source=src,
                target=tgt,
                relation=data['relation'],
                weight=data['weight'],
                metadata=data.get('metadata', {}),
                created_at=data.get('created_at', 0),
                invalid_at=data.get('invalid_at'),
            ))

        self.store.save_graph(nodes_dict, edges_list)

    def add_node(self, node_type: str, content: str, metadata: Dict[str, Any] = None) -> Node:
        """创建并向图中添加一个新节点。时间戳使用游戏世界时间。"""
        node = Node(type=node_type, content=content, metadata=metadata or {})
        node.created_at = self._game_day()
        self.nx_graph.add_node(node.id, data=node)
        self.save()
        return node

    def add_edge(self, source_id: str, target_id: str, relation: str,
                 weight: float = 1.0, metadata: Dict[str, Any] = None) -> Optional[Edge]:
        """在两个节点之间创建一条有向边。时间戳使用游戏世界时间。"""
        if not self.nx_graph.has_node(source_id) or not self.nx_graph.has_node(target_id):
            logger.warning(f"Cannot add edge: Nodes {source_id} or {target_id} missing.")
            return None

        self.nx_graph.add_edge(source_id, target_id,
                               relation=relation, weight=weight,
                               metadata=metadata or {},
                               created_at=self._game_day())
        self.save()

        return Edge(source=source_id, target=target_id, relation=relation,
                    weight=weight, metadata=metadata or {},
                    created_at=self._game_day())

    def get_node(self, node_id: str) -> Optional[Node]:
        """通过 ID 获取节点的有效数据载荷。"""
        if self.nx_graph.has_node(node_id):
            return self.nx_graph.nodes[node_id]['data']
        return None

    def find_nodes_by_type(self, node_type: str) -> List[Node]:
        """查找特定类型的所有节点（包含失效，调用方可自行过滤）。"""
        result = []
        for _, data in self.nx_graph.nodes(data=True):
            if data['data'].type == node_type:
                result.append(data['data'])
        return result

    # ==================== 生命周期管理 ====================

    def mark_node_deprecated(self, node_id: str) -> bool:
        """标记节点为失效。返回是否成功。"""
        if not self.nx_graph.has_node(node_id):
            return False
        self.nx_graph.nodes[node_id]['data'].invalid_at = self._game_day()
        self.save()
        return True

    def mark_edge_deprecated(self, source_id: str, target_id: str, relation: str = None) -> bool:
        """
        标记边为失效。若指定 relation，只标记匹配该 relation 的边；
        否则标记两节点之间所有方向的边。
        """
        marked = False
        for src, tgt in [(source_id, target_id), (target_id, source_id)]:
            if self.nx_graph.has_edge(src, tgt):
                edge_data = self.nx_graph.get_edge_data(src, tgt)
                if relation is None or edge_data.get('relation') == relation:
                    edge_data['invalid_at'] = self._game_day()
                    marked = True
        if marked:
            self.save()
        return marked

    def merge_nodes(self, keep_id: str, discard_id: str) -> bool:
        """
        合并两个节点：discard_id 的入边和出边转移到 keep_id，
        discard_id 标记为失效并记录 summarized_to。
        """
        if not self.nx_graph.has_node(keep_id) or not self.nx_graph.has_node(discard_id):
            return False

        keep_node = self.nx_graph.nodes[keep_id]['data']
        discard_node = self.nx_graph.nodes[discard_id]['data']

        # 转移入边
        for pred in list(self.nx_graph.predecessors(discard_id)):
            edge_data = dict(self.nx_graph.get_edge_data(pred, discard_id))
            if not self.nx_graph.has_edge(pred, keep_id):
                self.nx_graph.add_edge(pred, keep_id, **edge_data)

        # 转移出边
        for succ in list(self.nx_graph.successors(discard_id)):
            edge_data = dict(self.nx_graph.get_edge_data(discard_id, succ))
            if not self.nx_graph.has_edge(keep_id, succ):
                self.nx_graph.add_edge(keep_id, succ, **edge_data)

        # 标记 discard 节点
        discard_node.invalid_at = self._game_day()
        discard_node.summarized_to = keep_id
        keep_node.access_count += discard_node.access_count

        self.save()
        return True

    def remove_node_permanently(self, node_id: str) -> bool:
        """永久删除节点及其所有相连边。"""
        if not self.nx_graph.has_node(node_id):
            return False
        self.nx_graph.remove_node(node_id)
        self.save()
        return True

    def remove_edge_permanently(self, source_id: str, target_id: str) -> bool:
        """永久删除边。"""
        if not self.nx_graph.has_edge(source_id, target_id):
            return False
        self.nx_graph.remove_edge(source_id, target_id)
        self.save()
        return True

    # ==================== 批量查询 ====================

    def get_all_nodes(self) -> List[Node]:
        """返回图中所有有效（未失效）的 Node 对象。"""
        result = []
        for _, data in self.nx_graph.nodes(data=True):
            node = data['data']
            if getattr(node, 'invalid_at', None) is None:
                result.append(node)
        return result

    def get_all_edges(self) -> List[Edge]:
        """返回图中所有有效的 Edge 对象。"""
        result = []
        for src, tgt, data in self.nx_graph.edges(data=True):
            if data.get('invalid_at') is None:
                result.append(Edge(
                    source=src,
                    target=tgt,
                    relation=data.get('relation', ''),
                    weight=data.get('weight', 1.0),
                    metadata=data.get('metadata', {}),
                    created_at=data.get('created_at', 0),
                    invalid_at=data.get('invalid_at'),
                ))
        return result
