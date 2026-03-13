"""
图检索器 - 扩散激活与记忆上下文选择

实现了扩散激活（Spreading Activation）算法，用于在给定一组焦点节点
（如触发器、当前位置、当前任务）的基础上深挖和寻找上下文相关的记忆。
"""

import time
import networkx as nx
import logging
from typing import List, Set, Dict, Tuple

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
        TODO: 实现高级的艾宾浩斯（Ebbinghaus）遗忘曲线。
        目前返回一个简单的 基准值 + 访问加成。
        """
        # 占位符公式
        base = 1.0
        recency_bonus = 0.5 if (time.time() - node.last_accessed) < 3600 else 0.0
        frequency_bonus = min(node.access_count * 0.1, 1.0)
        return base + recency_bonus + frequency_bonus

    def spread_activation(self, start_node_ids: List[str], max_depth: int = 2, top_k: int = 10) -> List[Node]:
        """
        从 start_node_ids 起始点执行扩散激活算法。
        
        参数:
            start_node_ids: 当前上下文的焦点节点ID列表。
            max_depth: 遍历边的最大深度。
            top_k: 返回相关性最高的节点数量。
        """
        # 存储每个节点累积得分的字典
        activation_scores: Dict[str, float] = {}
        
        # 初始化起点节点
        q = [] # (节点ID, 当前能量, 当前深度)
        for nid in start_node_ids:
            if self.engine.nx_graph.has_node(nid):
                q.append((nid, 10.0, 0)) # 初始能量 = 10.0
                activation_scores[nid] = 10.0
                
        # 遍历图 (扩散，类似于广度优先搜索BFS)
        while q:
            current_id, energy, depth = q.pop(0)
            
            if depth >= max_depth:
                continue
                
            # 迭代相邻节点 (包含出边和入边，实现双向性)
            neighbors = list(self.engine.nx_graph.successors(current_id)) + list(self.engine.nx_graph.predecessors(current_id))
            for nbr_id in set(neighbors):
                # 计算跨边的衰减率
                # (TODO: 精确提取边的权重。目前假定衰减系数为0.5)
                edge_weight = 0.5 
                transferred_energy = energy * edge_weight
                
                # 更新得分
                if nbr_id not in activation_scores:
                    activation_scores[nbr_id] = 0.0
                activation_scores[nbr_id] += transferred_energy
                
                # 如果能量还足够大，且没有触及深度限制，继续传递
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
            # 检索时不忘更新访问计数
            node.access_count += 1
            node.last_accessed = time.time()
            result_nodes.append(node)
            
        self.engine.save() # 持久化 access_count 的更新数据
        return result_nodes
