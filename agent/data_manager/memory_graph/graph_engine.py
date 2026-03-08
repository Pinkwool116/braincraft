"""
图引擎 - 记忆管理与 NetworkX 封装

维护一个内存中的 NetworkX 有向图 (DiGraph)，处理节点/边的添加和删除。
作为记忆图配置的中心和唯一事实来源。
"""

import networkx as nx
import logging
from typing import List, Dict, Any, Optional

from .graph_types import Node, Edge
from .graph_store import GraphStore

logger = logging.getLogger(__name__)

class GraphEngine:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.store = GraphStore(agent_name)
        self.nx_graph = nx.DiGraph()
        
        self._initialize_from_store()

    def _initialize_from_store(self):
        """从存储中加载节点和边到 NetworkX 图中。"""
        nodes, edges = self.store.load_graph()
        
        for n_id, node in nodes.items():
            self.nx_graph.add_node(n_id, data=node)
            
        for edge in edges:
            # 仅在两个节点都实际存在时添加边（引用完整性）
            if self.nx_graph.has_node(edge.source) and self.nx_graph.has_node(edge.target):
                self.nx_graph.add_edge(
                    edge.source, 
                    edge.target, 
                    relation=edge.relation,
                    weight=edge.weight,
                    metadata=edge.metadata
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
                metadata=data['metadata']
            ))
            
        self.store.save_graph(nodes_dict, edges_list)

    def add_node(self, node_type: str, content: str, metadata: Dict[str, Any] = None) -> Node:
        """创建并向图中添加一个新节点。"""
        node = Node(type=node_type, content=content, metadata=metadata or {})
        self.nx_graph.add_node(node.id, data=node)
        self.save()
        return node

    def add_edge(self, source_id: str, target_id: str, relation: str, weight: float = 1.0, metadata: Dict[str, Any] = None) -> Optional[Edge]:
        """在两个节点之间创建一条有向边。"""
        if not self.nx_graph.has_node(source_id) or not self.nx_graph.has_node(target_id):
            logger.warning(f"Cannot add edge: Nodes {source_id} or {target_id} missing.")
            return None
            
        self.nx_graph.add_edge(source_id, target_id, relation=relation, weight=weight, metadata=metadata or {})
        self.save()
        
        return Edge(source=source_id, target=target_id, relation=relation, weight=weight, metadata=metadata or {})

    def get_node(self, node_id: str) -> Optional[Node]:
        """通过 ID 获取节点的有效数据载荷。"""
        if self.nx_graph.has_node(node_id):
            return self.nx_graph.nodes[node_id]['data']
        return None
        
    def find_nodes_by_type(self, node_type: str) -> List[Node]:
        """查找特定类型的所有节点。"""
        result = []
        for _, data in self.nx_graph.nodes(data=True):
            if data['data'].type == node_type:
                result.append(data['data'])
        return result
