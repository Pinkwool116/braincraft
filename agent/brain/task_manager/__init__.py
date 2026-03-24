"""
Task Manager

File-based task management for the agent.
Tasks are stored as markdown files that the agent reads and writes.
"""

from .task_file_manager import TaskFileManager

__all__ = ['TaskFileManager']
