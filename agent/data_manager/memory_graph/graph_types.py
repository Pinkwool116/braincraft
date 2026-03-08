"""
图记忆引擎的核心类型。

定义了知识/情景图的节点（Node）、边（Edge）以及基本模式。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time
import uuid


class NodeType:
    """
    记忆图谱中的节点类型。

    五种记忆不是图谱中的分区，而是检索视角：
    - 语义记忆：从 pattern / item 出发
    - 空间记忆：从 place 出发
    - 情节记忆：从 episode / event / time_anchor 出发
    - 社交记忆：从 agent 出发
    - 自我画像：从 reflection 出发
    """
    EVENT = "event"              # 单个显著事件
    EPISODE = "episode"          # 一段完整经历的概括
    PLACE = "place"              # 地点、区域（带坐标）
    AGENT = "agent"              # 人物/其他智能体
    ITEM = "item"                # 重要物品
    GOAL = "goal"                # 长期目标、愿望
    PATTERN = "pattern"          # 可复用的经验规则、教训
    EMOTION = "emotion"          # 情感
    ATTITUDE = "attitude"        # 对人/事的态度
    REFLECTION = "reflection"    # 自我认识、总结
    TIME_ANCHOR = "time_anchor"  # 时间参照点（"第N天"等）

    ALL = [
        EVENT, EPISODE, PLACE, AGENT, ITEM, GOAL,
        PATTERN, EMOTION, ATTITUDE, REFLECTION, TIME_ANCHOR,
    ]


class EdgeRelation:
    """记忆图谱中的边关系类型。保持通用，不为特定场景设计。"""
    # 空间
    NEAR = "NEAR"
    LOCATED_AT = "LOCATED_AT"
    # 时间
    HAPPENED_AT = "HAPPENED_AT"
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    ANCHORED_AT = "ANCHORED_AT"
    # 组成
    CONTAINS = "CONTAINS"
    PART_OF = "PART_OF"
    # 因果
    LED_TO = "LED_TO"
    CAUSED_BY = "CAUSED_BY"
    LEARNED_FROM = "LEARNED_FROM"
    # 关联
    INVOLVES = "INVOLVES"
    RELATED_TO = "RELATED_TO"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    # 社交
    KNOWS = "KNOWS"
    FEELS_ABOUT = "FEELS_ABOUT"
    COOPERATED_WITH = "COOPERATED_WITH"
    # 类属
    IS_A = "IS_A"
    HAS_PROPERTY = "HAS_PROPERTY"


@dataclass
class Node:
    """
    记忆图中的基础实体。
    可以表示事件、地点、经历、模式等（类型见 NodeType）。
    """
    type: str          # 节点类型，应为 NodeType 中的值
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

