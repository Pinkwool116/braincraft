"""
PerceptionManager — Coordinates two independent perception pipelines.

  1. EventTicker (every 2s, pure code):
     Consumes discrete events (entity/sound/block/weather) from PerceptionBuffer
     → aggregates → writes observation to WorkingMemory.

  2. PerceptionLLM (every 300s, Flash LLM):
     Receives scan snapshots from JS via handle_scan() (separate channel)
     → every 300s checks latest scan → terrain description → WorkingMemory.

Scan data and event data never mix. Scans are snapshots, not continuous.
"""

import asyncio
import logging
from typing import Optional

from .perception_buffer import PerceptionBuffer
from .event_ticker import EventTicker

logger = logging.getLogger(__name__)


class PerceptionManager:
    """Coordinates perception buffer, EventTicker, and (optionally) PerceptionLLM."""

    def __init__(self, memory_router, llm=None,
                 get_position=None,
                 get_health=None,
                 get_food=None,
                 request_scan=None,
                 ticker_interval: float = 2.0,
                 terrain_interval: float = 30.0,
                 prompt_logger=None,
                 prompt_manager=None):
        self.buffer = PerceptionBuffer(max_size=500)
        self.ticker = EventTicker()
        self.memory_router = memory_router
        self._get_position = get_position    # () → {'x','y','z'} | None
        self._get_health = get_health        # () → float | None
        self._get_food = get_food            # () → float | None
        self._request_scan = request_scan    # async (...) → None (triggers JS full scan)

        # PerceptionLLM is optional (requires LLM)
        self.perception_llm = None
        if llm:
            from .perception_llm import PerceptionLLM
            self.perception_llm = PerceptionLLM(llm, prompt_logger=prompt_logger, prompt_manager=prompt_manager)

        # Scan snapshots (separate from event buffer — scans are snapshots, not events)
        self._scan_samples: list = []
        self._block_stats: Optional[dict] = None
        self._scan_generation = 0          # incremented each time new scan arrives
        self._last_analyzed_generation = -1

        self._ticker_interval = ticker_interval
        self._terrain_interval = terrain_interval
        self._terrain_failures = 0

        self._running = False
        self._ticker_task: Optional[asyncio.Task] = None
        self._terrain_task: Optional[asyncio.Task] = None

    # ---- lifecycle ----

    async def start(self):
        """Start background loops."""
        self._running = True
        self._ticker_task = asyncio.create_task(self._ticker_loop())
        if self.perception_llm:
            self._terrain_task = asyncio.create_task(self._terrain_loop())
        logger.info("PerceptionManager started (ticker=%.0fs, terrain=%.0fs)",
                    self._ticker_interval, self._terrain_interval)

    async def stop(self):
        """Stop background loops."""
        self._running = False
        for task in (self._ticker_task, self._terrain_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("PerceptionManager stopped")

    # ---- scan input (separate channel from events) ----

    def handle_scan(self, scan_type: str, data: dict):
        """Receive a scan snapshot from JS PerceptionWorker.

        Called from brain_coordinator's perception_scan IPC handler.
        Scans are snapshots, not continuous events — they don't go through the event buffer.
        """
        if scan_type == 'full_scan':
            samples = data.get('samples', [])
            if samples:
                self._scan_samples = samples
                self._scan_generation += 1
        elif scan_type == 'block_stats':
            self._block_stats = data.get('stats', {})

    # ---- ticker loop (every 2s, pure code, events only) ----

    async def _ticker_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self._ticker_interval)

                # Check vitals changes every tick (independent of events)
                if self._get_health and self._get_food:
                    try:
                        health = self._get_health()
                        food = self._get_food()
                        if health is not None and food is not None:
                            vitals_text = self.ticker.check_vitals(health, food)
                            if vitals_text:
                                self._write_observation(vitals_text)
                    except Exception:
                        pass  # best-effort, don't block the ticker

                if self.buffer.is_empty:
                    continue
                events = await self.buffer.consume()
                text = self.ticker.aggregate(events)
                if text:
                    self._write_observation(text)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"EventTicker loop error: {e}", exc_info=True)

    # ---- terrain loop (every 30s, Flash LLM, scan snapshots only) ----

    async def _terrain_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self._terrain_interval)
                await self._maybe_analyze_terrain()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"PerceptionLLM loop error: {e}", exc_info=True)

    async def _maybe_analyze_terrain(self):
        """Check if we have a fresh scan snapshot worth analyzing."""
        if not self.perception_llm:
            return
        if not self._scan_samples:
            return
        # Skip if no new scan data since last analysis
        if self._scan_generation <= self._last_analyzed_generation:
            return

        pos = self._get_position() if self._get_position else None
        biome = 'unknown'
        time_label = 'Day'
        # Try to read biome/time from memory context (best-effort)
        try:
            ctx = self.memory_router.working_memory.context
            biome = ctx.get('biome', 'unknown')
            time_label = ctx.get('time_label', 'Day')
        except Exception:
            pass

        scan_data = {
            'ray_samples': self._scan_samples,
            'block_stats': self._block_stats,
            'biome': biome,
            'time_label': time_label,
        }

        try:
            text = await self.perception_llm.analyze(scan_data)
            self._last_analyzed_generation = self._scan_generation
            if text:
                self._write_observation(text)
                self._terrain_failures = 0
        except Exception as e:
            self._terrain_failures += 1
            logger.warning(f"Terrain analysis failed ({self._terrain_failures}/3): {e}")

    async def force_analyze_terrain(
            self,
            focus: str = "",
            fresh_scan: bool = True,
            include_block_stats: bool = True) -> Optional[dict]:
        """Force an immediate terrain analysis using the latest scan data.

        Unlike _maybe_analyze_terrain, this does not check _scan_generation.
        If requested or no scan data is available, triggers a JS-side full scan and waits
        for the data to arrive (up to 5s timeout).
        Used by the scan_terrain tool for on-demand macro observation.
        """
        if not self.perception_llm:
            return None

        start_generation = self._scan_generation
        if fresh_scan or not self._scan_samples:
            # Trigger JS-side full scan and wait for data
            if self._request_scan:
                try:
                    await self._request_scan(include_block_stats=include_block_stats)
                except Exception:
                    pass  # best-effort, proceed to check if data arrived
                # Wait for scan data, polling every 200ms, up to 5 seconds
                import asyncio as _asyncio
                for _ in range(25):
                    await _asyncio.sleep(0.2)
                    if self._scan_samples and (not fresh_scan or self._scan_generation > start_generation):
                        break
            if not self._scan_samples:
                return None  # still no data after waiting
            if fresh_scan and self._scan_generation <= start_generation:
                return None

        pos = self._get_position() if self._get_position else None
        biome = 'unknown'
        time_label = 'Day'
        try:
            ctx = self.memory_router.working_memory.context
            biome = ctx.get('biome', 'unknown')
            time_label = ctx.get('time_label', 'Day')
        except Exception:
            pass

        scan_data = {
            'ray_samples': self._scan_samples,
            'block_stats': self._block_stats if include_block_stats else None,
            'biome': biome,
            'time_label': time_label,
            'focus': focus,
        }

        try:
            text = await self.perception_llm.analyze(scan_data)
            self._last_analyzed_generation = self._scan_generation
            return {
                'description': text,
                'focus': focus,
                'fresh': bool(fresh_scan),
                'scan_generation': self._scan_generation,
                'biome': biome,
                'time_label': time_label,
                'include_block_stats': bool(include_block_stats),
            } if text else None
        except Exception as e:
            logger.warning(f"Forced terrain analysis failed: {e}")
            return None

    async def summarize_inspect_surroundings(
            self,
            summary_input: dict,
            focus: str = "",
    ) -> Optional[str]:
        """Summarize an inspect_surroundings scan result via the terrain analyzer LLM.

        Delegates to PerceptionLLM which owns the LLM, prompt_manager, and prompt_logger.
        Mirrors force_analyze_terrain() — the tool is a thin wrapper, logic lives here.
        """
        if not self.perception_llm:
            return None
        return await self.perception_llm.summarize_inspect_surroundings(summary_input, focus)

    # ---- helpers ----

    def _write_observation(self, text: str):
        """Write an observation to WorkingMemory (consolidate_weight=0)."""
        try:
            self.memory_router.log(
                entry_type='observation',
                content=text,
                consolidate_weight=0
            )
        except Exception as e:
            logger.error(f"Failed to write observation: {e}")

    @staticmethod
    def _distance(a: dict, b: dict) -> float:
        return ((a.get('x', 0) - b.get('x', 0)) ** 2 +
                (a.get('y', 0) - b.get('y', 0)) ** 2 +
                (a.get('z', 0) - b.get('z', 0)) ** 2) ** 0.5
