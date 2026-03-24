"""
Brain Module

Agent Loop + Reflex architecture.
(Phase 1: cleaned — old layer classes removed)
"""

from .brain_coordinator import BrainCoordinator
from .execution_coordinator import ExecutionCoordinator

__all__ = [
    'BrainCoordinator',
    'ExecutionCoordinator',
]
