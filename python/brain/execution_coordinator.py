"""
Execution Coordinator

Unified execution management for the three-layer brain system.
Prevents concurrent execution conflicts.
Similar to the original project's ActionManager.

Responsibilities:
- Manage execution priorities
- Handle interruptions and resumptions
- Coordinate action execution across low-level, mid-level, and high-level brains
"""

import asyncio
import logging
from typing import Dict, Any, Callable, Optional, List

logger = logging.getLogger(__name__)

class ExecutionCoordinator:
    """
    Unified execution manager for the three-layer brain system
    
    Priority levels (high to low):
    1. low_reflex (Low-level reflexes - survival related)
    2. low_mode (Low-level modes - autonomous behaviors)
    3. unstuck (Stuck detection)
    4. mid (Mid-level tasks)
    5. high (High-level contemplation)
    """
    
    def __init__(self, shared_state, high_brain=None, ipc_server=None):
        """
        Initialize execution coordinator
        
        Args:
            shared_state: Shared state object
            high_brain: High-level brain reference (for interrupting contemplation)
            ipc_server: IPC server reference (for synchronizing interrupt flag to JavaScript)
        """
        self.shared_state = shared_state
        self.high_brain = high_brain
        self.ipc_server = ipc_server
        
        # Priority definition (higher number = higher priority)
        self.priority_map = {
            'low_reflex': 5,   # Highest priority - survival reflexes
            'low_mode': 4,     # Low-level modes (combat, item collecting, etc.)
            'unstuck': 3,      # Stuck detection
            'chat': 3,         # Chat responses (same as unstuck, can interrupt mid-level)
            'mid': 2,          # Mid-level tasks
            'high': 1,         # High-level contemplation
        }
        
        # Track current executing task for immediate cancellation
        self.current_task = None
        self.current_layer = None
        
        logger.info("ExecutionCoordinator initialized")
    
    async def execute_action(self, 
                            layer: str, 
                            label: str, 
                            action_fn: Callable, 
                            can_interrupt: Optional[List[str]] = None, 
                            auto_resume: bool = True) -> Dict[str, Any]:
        """
        Unified interface for executing actions
        
        Args:
            layer: Execution layer ('high' | 'mid' | 'low_reflex' | 'low_mode' | 'unstuck')
            label: Action label (for logging and debugging)
            action_fn: Execution function (async)
            can_interrupt: Which layers can interrupt this action (e.g. ['low_reflex', 'low_mode'])
                          None means cannot be interrupted
            auto_resume: Whether to auto-resume interrupted action after completion
        
        Returns:
            {
                'success': bool,      # Whether execution succeeded
                'result': Any,        # Execution result
                'blocked': bool,      # Whether blocked (insufficient priority)
                'error': str          # Error message (if any)
            }
        """
        # 1. Check if there's a currently executing action
        executing_layer = await self.shared_state.get('executing_layer')
        
        if executing_layer:
            # Check priority
            if not self._can_interrupt(executing_layer, layer):
                logger.debug(f"{layer}:{label} blocked by {executing_layer}")
                return {'success': False, 'blocked': True}
            
            # ⚡ IMMEDIATE CANCELLATION: Cancel the current task
            if self.current_task and not self.current_task.done():
                logger.warning(f"🛑 Cancelling {executing_layer} task to execute higher priority {layer}:{label}")
                
                # Save reference to task before it gets cleared
                task_to_cancel = self.current_task
                
                # Set interrupt flag for JavaScript code execution (like original project)
                await self.shared_state.update('interrupt_code', True)
                
                # Sync flag to JavaScript immediately
                if self.ipc_server:
                    await self.ipc_server.send_command({
                        'type': 'set_interrupt_flag',
                        'data': {'value': True}
                    })
                
                logger.debug("Set interrupt_code flag to True (Python + JavaScript)")
                
                # Cancel Python-side task
                task_to_cancel.cancel()
                
                # Poll waiting for execution to complete (like original ActionManager.stop())
                max_wait = 5.0  # Maximum 5 seconds
                poll_interval = 0.1  # Check every 100ms
                waited = 0
                while waited < max_wait and not task_to_cancel.done():
                    await asyncio.sleep(poll_interval)
                    waited += poll_interval
                    if waited % 1.0 < poll_interval:  # Log every second
                        logger.debug(f"Waiting for {executing_layer} to stop... {waited:.1f}s")
                
                # Clear interrupt flag (Python + JavaScript)
                await self.shared_state.update('interrupt_code', False)
                if self.ipc_server:
                    await self.ipc_server.send_command({
                        'type': 'set_interrupt_flag',
                        'data': {'value': False}
                    })
                
                logger.debug("Cleared interrupt_code flag (Python + JavaScript)")
                
                # Check if task actually stopped
                if not task_to_cancel.done():
                    logger.error(f"Failed to cancel {executing_layer} task after {max_wait}s")
                else:
                    logger.info(f"✅ Successfully interrupted {executing_layer} in {waited:.1f}s")
            
            # Save interrupted action info
            await self._save_interrupted_action(executing_layer, layer)
        
        # 2. Set current execution state
        await self.shared_state.update('executing_layer', layer)
        await self.shared_state.update('current_action', label)
        await self.shared_state.update('action_label', label)
        
        # 3. Create and execute action as a cancellable task
        self.current_layer = layer
        self.current_task = asyncio.create_task(action_fn())
        
        try:
            result = await self.current_task
            
            # 4. Execution complete, clear state
            await self.shared_state.update('executing_layer', None)
            await self.shared_state.update('current_action', None)
            self.current_task = None
            self.current_layer = None
            
            # 5. Resume interrupted action
            if auto_resume:
                await self._resume_interrupted_action()
            
            return {'success': True, 'result': result, 'blocked': False}
            
        except asyncio.CancelledError:
            # Task was cancelled by higher priority action
            logger.info(f"⚠️ {layer}:{label} was cancelled by higher priority action")
            await self.shared_state.update('executing_layer', None)
            await self.shared_state.update('current_action', None)
            self.current_task = None
            self.current_layer = None
            return {'success': False, 'cancelled': True, 'blocked': False}
            
        except Exception as e:
            logger.error(f"Error executing {layer}:{label}: {e}", exc_info=True)
            await self.shared_state.update('executing_layer', None)
            await self.shared_state.update('current_action', None)
            self.current_task = None
            self.current_layer = None
            return {'success': False, 'error': str(e), 'blocked': False}
    
    def _can_interrupt(self, current_layer: str, new_layer: str) -> bool:
        """
        Check if new action can interrupt current action
        
        Args:
            current_layer: Currently executing layer
            new_layer: New action's layer
        
        Returns:
            True if can interrupt, False otherwise
        """
        current_priority = self.priority_map.get(current_layer, 0)
        new_priority = self.priority_map.get(new_layer, 0)
        
        return new_priority > current_priority
    
    async def _save_interrupted_action(self, executing_layer: str, interrupting_layer: str):
        """
        Save interrupted action information
        
        Args:
            executing_layer: Layer being interrupted
            interrupting_layer: Interrupting layer
        """
        current_action = await self.shared_state.get('current_action')
        current_label = await self.shared_state.get('action_label')
        
        interrupted_info = {
            'layer': executing_layer,
            'label': current_label,
            'can_resume': True  # Default: can resume
        }
        
        # If mid-level task, save step_index
        if executing_layer == 'mid':
            task_plan = await self.shared_state.get('task_plan')
            if task_plan:
                interrupted_info['step_index'] = task_plan.get('current_step_index')
        
        await self.shared_state.update('interrupted_action', interrupted_info)
        await self.shared_state.update('interrupted_by', interrupting_layer)
        
        logger.warning(f"⚠️ {interrupting_layer} interrupting {executing_layer}:{current_label}")
        
        # If interrupting high-level contemplation, call high-level's interrupt mechanism
        if executing_layer == 'high' and self.high_brain:
            try:
                await self.high_brain._interrupt_contemplation()
                logger.info("💾 High-level contemplation interrupted and saved")
            except Exception as e:
                logger.error(f"Error interrupting high-level contemplation: {e}")
    
    async def _resume_interrupted_action(self):
        """
        Resume interrupted action
        
        Depending on the interrupted action's layer, use different resume strategies:
        - mid: Set mid_task_resume_requested flag
        - high: Call high-level's resume contemplation method
        """
        interrupted = await self.shared_state.get('interrupted_action')
        if not interrupted or not interrupted.get('can_resume'):
            # Clear interrupt info
            await self.shared_state.update('interrupted_action', None)
            await self.shared_state.update('interrupted_by', None)
            return
        
        layer = interrupted.get('layer')
        
        if layer == 'mid':
            # Notify mid-level to resume task
            step_index = interrupted.get('step_index', 'unknown')
            await self.shared_state.update('mid_task_resume_requested', True)
            logger.info(f"✅ Resuming interrupted mid-level task at step {step_index}")
        
        elif layer == 'high':
            # Resume high-level contemplation (through high-level's mechanism)
            if self.high_brain:
                try:
                    await self.high_brain._resume_contemplation()
                    logger.info("✅ Resuming interrupted high-level contemplation")
                except Exception as e:
                    logger.error(f"Error resuming high-level contemplation: {e}")
        
        # Clear interrupt info
        await self.shared_state.update('interrupted_action', None)
        await self.shared_state.update('interrupted_by', None)
    
    def get_priority(self, layer: str) -> int:
        """
        Get priority of specified layer
        
        Args:
            layer: Layer name
        
        Returns:
            Priority number (higher is more priority)
        """
        return self.priority_map.get(layer, 0)
