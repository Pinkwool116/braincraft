"""
图记忆引擎的核心类型。

定义了知识/情景图的节点（Node）、边（Edge）以及基本模式。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time
import uuid


@dataclass
class Node:
    """
    记忆图中的基础实体。
    可以表示事件、地点等。
    """
    type: str          # 例如：'event'（事件）, 'place'（地点）
    content: str       # 核心文本内容或描述符
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 可选的ID分配，如果未提供则自动生成
    id: str = field(default_factory=lambda: f"node_{uuid.uuid4().hex[:8]}")
    
    # 用于扩散激活模型的使用指标数据（记忆衰退与强化）
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "metadata": self.metadata,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "created_at": self.created_at
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Node':
        return cls(**data)


@dataclass
class Edge:
    """
    两个节点之间的有向关系。
    """
    source: str        # 源节点ID
    target: str        # 目标节点ID
    relation: str      # 例如：'HAPPENED_AT'（发生在）, 'SERVES_GOAL'（服务于目标）, 'IS_A'（属于）
    weight: float = 1.0  # 连接的重要性/强度
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "weight": self.weight,
            "metadata": self.metadata
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Edge':
        return cls(**data)

