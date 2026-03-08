"""
图存储 - 文件系统持久化

将节点按特定类型划分存入不同的文件中（如 nodes/events.json, nodes/places.json），
并将边缘关系存入 edges/relationships.json。
这保留了干净分块的文件存储外观，但在运行时作为单一整体图进行处理。
"""

import os
import json
import logging
from typing import Dict, List, Tuple
from .graph_types import Node, Edge

logger = logging.getLogger(__name__)

class GraphStore:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.base_dir = os.path.join("bots", agent_name, "memory_graph")
        self.nodes_dir = os.path.join(self.base_dir, "nodes")
        self.edges_dir = os.path.join(self.base_dir, "edges")
        
        # 确保目录存在
        os.makedirs(self.nodes_dir, exist_ok=True)
        os.makedirs(self.edges_dir, exist_ok=True)
        
        self.edges_file = os.path.join(self.edges_dir, "relationships.json")

    def _get_node_file_path(self, node_type: str) -> str:
        """返回特定节点类型的文件存放路径。使用复数形式让文件名更优雅。"""
        return os.path.join(self.nodes_dir, f"{node_type}s.json")

    def load_graph(self) -> Tuple[Dict[str, Node], List[Edge]]:
        """从磁盘加载所有的节点和边。"""
        nodes: Dict[str, Node] = {}
        edges: List[Edge] = []
        
        # 1. 加载节点
        for filename in os.listdir(self.nodes_dir):
            if not filename.endswith('.json'):
                continue
            path = os.path.join(self.nodes_dir, filename)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for node_data in data:
                        n = Node.from_dict(node_data)
                        nodes[n.id] = n
            except Exception as e:
                logger.error(f"Failed to load nodes from {path}: {e}")
                
        # 2. 加载边
        if os.path.exists(self.edges_file):
            try:
                with open(self.edges_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for edge_data in data:
                        edges.append(Edge.from_dict(edge_data))
            except Exception as e:
                logger.error(f"Failed to load edges from {self.edges_file}: {e}")
                
        return nodes, edges

    def save_graph(self, nodes: Dict[str, Node], edges: List[Edge]) -> None:
        """将图持久化保存到磁盘，将节点按照自身的 type 进行分区存储。"""
        # 1. 按类型将节点分组
        nodes_by_type: Dict[str, List[Dict]] = {}
        for node in nodes.values():
            n_type = node.type
            if n_type not in nodes_by_type:
                nodes_by_type[n_type] = []
            nodes_by_type[n_type].append(node.to_dict())
            
        # 写入节点文件
        for n_type, node_list in nodes_by_type.items():
            path = self._get_node_file_path(n_type)
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(node_list, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to save nodes to {path}: {e}")
                
        # 2. 保存边
        try:
            with open(self.edges_file, 'w', encoding='utf-8') as f:
                edge_data = [e.to_dict() for e in edges]
                json.dump(edge_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save edges: {e}")
