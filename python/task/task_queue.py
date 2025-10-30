"""
Task Queue

Manages task queue for mid-level brain execution.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)

class Task:
    """Task data structure"""
    
    def __init__(self, name: str, task_type: str, params: Dict[str, Any] = None):
        """
        Initialize task
        
        Args:
            name: Task name/description
            task_type: Type of task (collect, craft, build, etc.)
            params: Task parameters
        """
        self.id = f"task_{datetime.now().timestamp()}"
        self.name = name
        self.type = task_type
        self.params = params or {}
        self.retry_count = 0
        self.created_at = datetime.now()
        self.status = 'pending'  # pending, executing, completed, failed
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'params': self.params,
            'retry_count': self.retry_count,
            'created_at': self.created_at.isoformat(),
            'status': self.status
        }

class TaskQueue:
    """
    Task queue manager
    
    Maintains a queue of tasks to be executed by mid-level brain.
    """
    
    def __init__(self, config):
        """
        Initialize task queue
        
        Args:
            config: Configuration object
        """
        self.config = config
        self.queue = deque()
        self.completed_tasks = []
        self.failed_tasks = []
        self._lock = asyncio.Lock()
        
        logger.info("Task queue initialized")
    
    async def add(self, task: Task):
        """
        Add task to queue
        
        Args:
            task: Task to add
        """
        async with self._lock:
            self.queue.append(task)
            logger.info(f"Task added to queue: {task.name} (queue size: {len(self.queue)})")
    
    async def add_multiple(self, tasks: List[Task]):
        """
        Add multiple tasks to queue
        
        Args:
            tasks: List of tasks to add
        """
        async with self._lock:
            self.queue.extend(tasks)
            logger.info(f"Added {len(tasks)} tasks to queue (queue size: {len(self.queue)})")
    
    def peek(self) -> Optional[Task]:
        """
        Peek at next task without removing it
        
        Returns:
            Next task or None if queue is empty
        """
        if self.queue:
            return self.queue[0]
        return None
    
    async def pop(self) -> Optional[Task]:
        """
        Remove and return next task
        
        Returns:
            Next task or None if queue is empty
        """
        async with self._lock:
            if self.queue:
                task = self.queue.popleft()
                task.status = 'executing'
                logger.debug(f"Task popped from queue: {task.name}")
                return task
            return None
    
    async def complete(self, task: Task):
        """
        Mark task as completed
        
        Args:
            task: Completed task
        """
        async with self._lock:
            task.status = 'completed'
            self.completed_tasks.append(task)
            logger.info(f"Task completed: {task.name}")
    
    async def fail(self, task: Task, reason: str = None):
        """
        Mark task as failed
        
        Args:
            task: Failed task
            reason: Failure reason (optional)
        """
        async with self._lock:
            task.status = 'failed'
            if reason:
                task.params['failure_reason'] = reason
            self.failed_tasks.append(task)
            logger.warning(f"Task failed: {task.name} - {reason}")
    
    async def requeue(self, task: Task):
        """
        Re-add task to queue (for retries)
        
        Args:
            task: Task to requeue
        """
        async with self._lock:
            task.retry_count += 1
            task.status = 'pending'
            self.queue.append(task)
            logger.info(f"Task requeued: {task.name} (retry {task.retry_count})")
    
    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return len(self.queue) == 0
    
    def size(self) -> int:
        """Get queue size"""
        return len(self.queue)
    
    async def clear(self):
        """Clear all tasks from queue"""
        async with self._lock:
            self.queue.clear()
            logger.info("Task queue cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics
        
        Returns:
            Dictionary with queue stats
        """
        return {
            'pending': len(self.queue),
            'completed': len(self.completed_tasks),
            'failed': len(self.failed_tasks),
            'total': len(self.queue) + len(self.completed_tasks) + len(self.failed_tasks)
        }
