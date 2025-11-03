"""
Task Stack Manager

Manages the lifecycle of the task stack, including pushing, popping,
and modifying task plans.
"""
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class TaskStackManager:
    def __init__(self, shared_state, persistence):
        self.shared_state = shared_state
        self.persistence = persistence
        self.task_stack: List[Dict[str, Any]] = []

    def get_task_stack(self) -> List[Dict[str, Any]]:
        """Returns the current task stack."""
        return self.task_stack

    def get_active_task(self) -> Optional[Dict[str, Any]]:
        """Returns the active task (top of the stack) or None."""
        if not self.task_stack:
            return None
        return self.task_stack[-1]

    async def push_task_plan(self, task_plan: Dict[str, Any]):
        """Adds a new task plan to the top of the stack."""
        self.task_stack.append(task_plan)
        await self._update_shared_state_with_active_task()
        self.persistence.save_state(self.task_stack)
        logger.info("Pushed new task to stack. New active task: %s", task_plan.get('goal'))

    async def replace_task_stack(self, new_task_plans: List[Dict[str, Any]]):
        """Replaces the entire task stack with a new list of plans."""
        self.task_stack = new_task_plans
        await self._update_shared_state_with_active_task()
        self.persistence.save_state(self.task_stack)
        active_task = self.get_active_task()
        logger.info("Replaced task stack. New active task: %s", active_task.get('goal') if active_task else "None")

    async def replace_active_task(self, new_task_plan: Dict[str, Any]):
        """Replaces the active task (top of stack) with a new task plan."""
        if not self.task_stack:
            # If stack is empty, just push the new task
            await self.push_task_plan(new_task_plan)
            return
        
        # Replace the last item (active task) with the new one
        self.task_stack[-1] = new_task_plan
        await self._update_shared_state_with_active_task()
        self.persistence.save_state(self.task_stack)
        logger.info("Replaced active task with: %s", new_task_plan.get('goal'))

    async def discard_active_task(self, reason: str = None) -> Optional[Dict[str, Any]]:
        """Discards the active task and returns it."""
        if not self.task_stack:
            return None
        discarded_task = self.task_stack.pop()
        await self._update_shared_state_with_active_task()
        self.persistence.save_state(self.task_stack)
        logger.info("Discarded active task: %s", discarded_task.get('goal'))
        return discarded_task

    async def mark_task_completed(self):
        """Marks the current active task as completed and removes it from the stack."""
        if not self.task_stack:
            return
        completed_task = self.task_stack.pop()
        completed_task['status'] = 'completed'
        logger.info("✅ Task completed: %s", completed_task.get('goal'))
        
        # Potentially add to a list of completed tasks in memory manager here
        
        await self._update_shared_state_with_active_task()
        self.persistence.save_state(self.task_stack)

    async def mark_step_completed(self, step_index: int):
        """Marks a step as completed and advances to the next, or completes the task."""
        active_task = self.get_active_task()
        if not active_task:
            return

        if step_index != active_task.get('current_step_index'):
            logger.warning("Attempted to mark step %d as completed, but active step is %d",
                        step_index, active_task.get('current_step_index'))
            return

        total_steps = len(active_task.get('steps', []))
        if active_task['current_step_index'] < total_steps - 1:
            active_task['current_step_index'] += 1
            logger.info("Advanced to next step %d/%d",
                        active_task['current_step_index'] + 1, total_steps)
        else:
            await self.mark_task_completed()

        await self._update_shared_state_with_active_task()
        self.persistence.save_state(self.task_stack)

    async def update_active_task_step(self, step_index: int, status: str, failure_reason: Optional[str] = None):
        """Updates the status and failure reason of a specific step in the active task."""
        active_task = self.get_active_task()
        if not active_task:
            return

        steps = active_task.get('steps', [])
        if 0 <= step_index < len(steps):
            steps[step_index]['status'] = status
            if failure_reason:
                if 'failures' not in steps[step_index]:
                    steps[step_index]['failures'] = []
                steps[step_index]['failures'].append(failure_reason)
            
            await self._update_shared_state_with_active_task()
            self.persistence.save_state(self.task_stack)
            logger.debug("Updated step %d status to %s", step_index, status)

    async def _update_shared_state_with_active_task(self):
        """Updates the shared state with the current active task and stack summary."""
        active_task = self.get_active_task()
        await self.shared_state.update('active_task', active_task)
        
        summary = self.generate_task_stack_summary()
        await self.shared_state.update('task_stack_summary', summary)

    def generate_task_stack_summary(self) -> str:
        """Generates a string summary of the current task stack for prompts."""
        if not self.task_stack:
            return "The task stack is empty."

        summary_lines = ["Current task stack (top to bottom):"]
        for i, task in enumerate(reversed(self.task_stack)):
            prefix = " -> " if i > 0 else "   "
            status = f" (step {task.get('current_step_index', 0) + 1}/{len(task.get('steps', []))})"
            summary_lines.append(f"{prefix}[{i+1}] {task.get('goal', 'Untitled Task')}{status}")
        
        return "\n".join(summary_lines)

    def load_from_persistence(self, task_stack: List[Dict[str, Any]]):
        """Loads the task stack from a persisted state."""
        self.task_stack = task_stack
        logger.info("Task stack loaded from persistence. %d tasks.", len(self.task_stack))
        # No need to save here, just update shared state
        # Use asyncio.create_task if used in a non-async context at startup
        import asyncio
        asyncio.create_task(self._update_shared_state_with_active_task())
