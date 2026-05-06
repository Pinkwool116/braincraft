"""
Scan Terrain Tool

Triggers an immediate LLM-based terrain analysis on demand.
Complements the passive $NEARBY_BLOCKS data with semantic understanding
of terrain type, lighting, resources, and threats.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class ScanTerrainTool:
    """
    Tool: scan_terrain

    Trigger an immediate macro-level terrain scan using the perception LLM.
    Returns a natural language description of the surrounding environment.
    """

    name: str = "scan_terrain"
    description: str = (
        "主动扫描周围地形，返回地形类型、光照条件、资源分布、威胁评估等自然语言描述。"
        "用于需要宏观了解周围环境时，与被动显示的附近方块数据互补。"
    )

    def __init__(self, perception_manager):
        """
        Args:
            perception_manager: PerceptionManager instance (can be None)
        """
        self.perception_manager = perception_manager

    async def execute(self, args: dict) -> dict:
        """
        Trigger an immediate terrain analysis.

        Args:
            args: {} (no arguments needed)

        Returns:
            {'success': bool, 'description': str}
        """
        if self.perception_manager is None:
            return {'success': False, 'error': 'Perception system not available'}

        try:
            text = await self.perception_manager.force_analyze_terrain()
            if text:
                return {'success': True, 'description': text}
            else:
                return {'success': False,
                        'error': '地形扫描失败：已主动请求JS端扫描并等待5秒，仍未获取到数据。'
                                '可能刚启动不久或连接异常，稍后重试。'}
        except Exception as e:
            logger.error(f"ScanTerrainTool error: {e}")
            return {'success': False, 'error': str(e)}
