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

    事实性记忆（Factual）：
    - event: 在特定时间和地点发生的事情
    - place: 具有坐标的空间位置
    - person: 人物/玩家/智能体
    - item: 物品/方块/实体
    - time: 时间锚点

    经验性记忆（Experiential，由事实归纳而来）：
    - pattern: 可复用的经验规则
    - thought: 想法/反思/自我认知

    特殊类型：
    - community: 聚类算法生成的抽象概念节点
    """
    EVENT = "event"
    PLACE = "place"
    PERSON = "person"
    ITEM = "item"
    TIME = "time"
    PATTERN = "pattern"
    THOUGHT = "thought"
    COMMUNITY = "community"

    ALL = [EVENT, PLACE, PERSON, ITEM, TIME, PATTERN, THOUGHT, COMMUNITY]


class EdgeRelation:
    """记忆图谱中的边关系类型。"""
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
    COOPERATED_WITH = "COOPERATED_WITH"
    INTERACTED_WITH = "INTERACTED_WITH"
    # 类属
    IS_A = "IS_A"
    HAS_PROPERTY = "HAS_PROPERTY"
    # 归纳
    SUMMARIZED_FROM = "SUMMARIZED_FROM"


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
    last_accessed: float = field(default_factory=time.time)  # 现实时间，检索时效性
    created_at: float = field(default_factory=time.time)     # 游戏世界天数

    # 生命周期
    invalid_at: Optional[float] = None      # 失效时的游戏天数，非 None 表示已失效
    summarized_to: Optional[str] = None     # 被归纳到的目标节点 ID

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "metadata": self.metadata,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "created_at": self.created_at,
            "invalid_at": self.invalid_at,
            "summarized_to": self.summarized_to,
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
    relation: str      # 例如：'HAPPENED_AT', 'LOCATED_AT', 'IS_A'
    weight: float = 1.0  # 连接的重要性/强度
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 生命周期
    created_at: float = field(default_factory=time.time)   # 游戏世界天数
    invalid_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation,
            "weight": self.weight,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "invalid_at": self.invalid_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Edge':
        return cls(**data)
