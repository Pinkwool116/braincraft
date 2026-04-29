"""
TerrainAnalyzer — Flash LLM terrain understanding (every 30s).

Consumes active scan data (ray samples + block stats) and produces
a natural-language terrain description. Writes to WorkingMemory as observation.

This is the ONLY place Flash LLM is used in the perception pipeline.
Event aggregation is handled by EventTicker (pure code, no LLM).
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TerrainAnalyzer:
    """Flash LLM terrain understanding from ray-scan data."""

    def __init__(self, llm, model: str = "deepseek-v4-flash", prompt_logger=None, prompt_manager=None):
        self.llm = llm
        self.model = model
        self.prompt_logger = prompt_logger
        self.prompt_manager = prompt_manager
        self._last_result: str = ""
        self._consecutive_failures: int = 0
        self._max_failures: int = 3

    async def analyze(self, scan_data: dict) -> Optional[str]:
        """
        Analyze scan data and return a terrain description.

        Args:
            scan_data: {
                'ray_samples': [(yaw, pitch, block_name, distance, sky_light), ...],
                'block_stats': {...} or None,
                'biome': 'plains',
                'time_label': 'Day'
            }

        Returns:
            Natural-language terrain description, or None on failure.
        """
        samples = scan_data.get('ray_samples', [])
        if not samples:
            return None

        scan_text = self._format_scan(samples)

        block_stats = scan_data.get('block_stats')
        stats_text = self._format_stats(block_stats) if block_stats else ""

        biome = scan_data.get('biome', 'unknown')
        time_label = scan_data.get('time_label', 'Day')

        prompt = await self.prompt_manager.render(
            'perception/terrain_analysis.md',
            context={
                'BIOME': biome,
                'TIME_LABEL': time_label,
                'SCAN_TEXT': scan_text,
                'STATS_TEXT': stats_text,
            },
            strict=False
        )

        try:
            prompt_file = None
            if self.prompt_logger:
                prompt_file = self.prompt_logger.log_prompt(
                    prompt=prompt,
                    brain_layer="perception",
                    prompt_type="terrain_analysis"
                )

            response = await self.llm.send_request(
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.strip()

            if prompt_file and text:
                self.prompt_logger.update_response(prompt_file, text)

            if text:
                self._last_result = text
                self._consecutive_failures = 0
                return text
        except Exception as e:
            logger.warning(f"TerrainAnalyzer Flash API error: {e}")

        self._consecutive_failures += 1
        if self._consecutive_failures >= self._max_failures:
            logger.warning("TerrainAnalyzer degraded to template (3 consecutive failures)")
            return self._template_fallback(scan_data)
        return None

    def _format_scan(self, samples: list) -> str:
        """Format ray samples into a compact text block."""
        lines = []
        for s in samples:
            if not s:
                continue
            yaw = s.get('yaw', 0)
            pitch = s.get('pitch', 0)
            block = s.get('block_name', '?')
            dist = s.get('distance', 0)
            sl = s.get('sky_light', '?')
            lines.append(f"  方向{yaw}° 俯仰{pitch}° → {block} 距离{dist}格 天光{sl}")
        return '\n'.join(lines)

    def _format_stats(self, stats: dict) -> str:
        """Format block stats into a summary."""
        lines = ["\n区域方块统计 (8格半径):"]
        for name, info in sorted(stats.items(), key=lambda x: -x[1].get('count', 0)):
            count = info.get('count', 0)
            if count >= 3:
                dirs = info.get('directions', {})
                dir_text = '、'.join(f"{d}({c})" for d, c in sorted(dirs.items(), key=lambda x: -x[1])[:3])
                lines.append(f"  - {name}: {count}个 ({dir_text})")
        return '\n'.join(lines)

    def _template_fallback(self, scan_data: dict) -> str:
        """Fallback template-based terrain description (no LLM)."""
        samples = scan_data.get('ray_samples', [])
        biome = scan_data.get('biome', 'unknown')

        blocks_seen = {}
        for s in samples:
            if not s:
                continue
            name = s.get('block_name', 'air')
            blocks_seen[name] = blocks_seen.get(name, 0) + 1

        # Simple terrain heuristics
        has_water = 'water' in blocks_seen
        has_lava = 'lava' in blocks_seen
        has_trees = any('log' in b for b in blocks_seen)
        has_stone = 'stone' in blocks_seen
        cave = all(s.get('sky_light', 15) == 0 for s in samples if s and s.get('block_name') != 'air')

        parts = [f"当前处于{biome}生物群系。"]
        if cave:
            parts.append("周围天光为0，可能处于洞穴中。")
        if has_trees:
            parts.append("附近检测到树木。")
        if has_water:
            parts.append("附近有水源。")
        if has_lava:
            parts.append("警告：附近检测到熔岩！")
        if has_stone:
            parts.append("检测到石头，可能有矿洞。")

        return ''.join(parts)
