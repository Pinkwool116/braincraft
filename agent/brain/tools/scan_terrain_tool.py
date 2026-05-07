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
        "主动扫描周围地形，返回宏观地形结构、可通行方向、资源方向、危险因素和行动建议。"
        "参数: focus(可选，观察重点，如'找安全下矿入口'或'判断是否适合建临时基地'), "
        "fresh_scan(默认true，主动请求JS新扫描), include_block_stats(默认true)。"
        "用于理解地形结构；需要精确坐标时改用 inspect_surroundings。"
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
            args: {'focus': str, 'fresh_scan': bool, 'include_block_stats': bool}

        Returns:
            {'success': bool, 'description': str}
        """
        if self.perception_manager is None:
            return {'success': False, 'error': 'Perception system not available'}

        try:
            focus = str(args.get('focus', '')).strip()
            fresh_scan = args.get('fresh_scan', True)
            include_block_stats = args.get('include_block_stats', True)
            if isinstance(fresh_scan, str):
                fresh_scan = fresh_scan.lower() not in ('false', '0', 'no')
            if isinstance(include_block_stats, str):
                include_block_stats = include_block_stats.lower() not in ('false', '0', 'no')

            result = await self.perception_manager.force_analyze_terrain(
                focus=focus,
                fresh_scan=bool(fresh_scan),
                include_block_stats=bool(include_block_stats),
            )
            text = result.get('description') if isinstance(result, dict) else result
            if text:
                if isinstance(result, dict):
                    return {'success': True, **result}
                return {'success': True, 'description': text}
            else:
                return {'success': False,
                        'error': '地形扫描失败：已主动请求JS端扫描并等待5秒，仍未获取到数据。'
                                '可能刚启动不久或连接异常，稍后重试。'}
        except Exception as e:
            logger.error(f"ScanTerrainTool error: {e}")
            return {'success': False, 'error': str(e)}
