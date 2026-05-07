"""
PerceptionLLM — Flash LLM for perception understanding tasks.

Handles all LLM-backed perception analysis:
- Terrain analysis (every 30s): ray-scan data → natural-language terrain description
- Inspect surroundings summarization (on-demand): scan results → focused summary

This is the ONLY place Flash LLM is used in the perception pipeline.
Event aggregation is handled by EventTicker (pure code, no LLM).
"""

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PerceptionLLM:
    """LLM-backed perception analysis: terrain understanding + inspect surroundings summarization."""

    def __init__(self, llm, prompt_logger=None, prompt_manager=None):
        self.llm = llm
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
                'time_label': 'Day',
                'focus': 'optional observation focus'
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
        focus = scan_data.get('focus', '')

        prompt = await self.prompt_manager.render(
            'perception/terrain_analysis.md',
            context={
                'BIOME': biome,
                'TIME_LABEL': time_label,
                'SCAN_TEXT': scan_text,
                'STATS_TEXT': stats_text,
                'FOCUS': focus if focus else '无特定重点，客观描述整体地形。',
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
            logger.warning(f"PerceptionLLM Flash API error: {e}")

        self._consecutive_failures += 1
        if self._consecutive_failures >= self._max_failures:
            logger.warning("PerceptionLLM degraded to template (3 consecutive failures)")
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

    async def summarize_inspect_surroundings(self, summary_input: dict, focus: str) -> Optional[str]:
        """
        Summarize an inspect_surroundings scan result via Flash LLM.

        Args:
            summary_input: {request, summary, samples, invalid_targets, suggestions}
            focus: The observation focus from the original request.

        Returns:
            Natural-language summary text, or None on failure.
        """
        scan_data_json = json.dumps(summary_input, ensure_ascii=False, indent=2)

        prompt = await self.prompt_manager.render(
            'perception/inspect_surroundings_summary.md',
            context={
                'FOCUS': focus or '无特定重点，客观描述周围环境',
                'SCAN_DATA': scan_data_json,
            },
            strict=False,
        )

        try:
            prompt_file = None
            if self.prompt_logger:
                prompt_file = self.prompt_logger.log_prompt(
                    prompt=prompt,
                    brain_layer="perception",
                    prompt_type="inspect_surroundings_summary",
                )

            response = await self.llm.send_request(
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.strip()

            if prompt_file and text:
                self.prompt_logger.update_response(prompt_file, text)

            if text:
                return text
        except Exception as e:
            logger.warning(f"inspect_surroundings LLM summary failed: {e}")

        return None

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
