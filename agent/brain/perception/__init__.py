"""
Perception Module

EventTicker (pure code, no LLM) + TerrainAnalyzer (Flash LLM, deferred).
All observation entries write to WorkingMemory via MemoryRouter.
"""

from .perception_buffer import PerceptionBuffer
from .event_ticker import EventTicker
from .perception_manager import PerceptionManager

__all__ = ['PerceptionBuffer', 'EventTicker', 'PerceptionManager']
