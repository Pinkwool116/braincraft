"""
High-Level Brain

Responsible for:
- Strategic planning and long-term goals
- Experience summarization from mid-level brain
- Memory management
- Providing guidance to mid-level brain
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from data_manager.memory_manager import MemoryManager
from data_manager.mind_state_manager import MindStateManager
from prompts.prompt_logger import PromptLogger
from prompts.prompt_manager import PromptManager
from brain.mind_system.goal_hierarchy import GoalHierarchy
from brain.mind_system.self_awareness import SelfAwareness
from brain.mind_system.mental_state import MentalState
from brain.contemplation import ContemplationManager
from brain.task_stack.task_stack_manager import TaskStackManager
from brain.task_stack.task_persistence import TaskPersistence
from brain.task_stack.task_planner import TaskPlanner
from brain.task_stack.task_handler import TaskHandler

logger = logging.getLogger(__name__)

class HighLevelBrain:
    """
    High-level brain for strategic thinking
    
    Orchestrates the major components of the agent's mind, including
    task management, strategic planning, and self-reflection.
    """
    
    def __init__(self, shared_state, config, llm_model):
        """
        Initialize high-level brain and its components.
        """
        self.shared_state = shared_state
        self.config = config
        self.llm = llm_model
        
        agent_name = config.get('agent_name', 'BrainyBot')
        self.memory_manager = MemoryManager(agent_name)
        self.mind_state_manager = MindStateManager(agent_name)
        
        # Initialize Prompt Logger for debugging (controlled by config)
        enable_logging = config.get('enable_prompt_logging', False)
        self.prompt_logger = PromptLogger('bots', agent_name, enabled=enable_logging)
        
        # Initialize Task Stack Components
        self.task_persistence = TaskPersistence(self.mind_state_manager)
        self.task_stack_manager = TaskStackManager(self.shared_state, self.task_persistence)
        self.task_planner = TaskPlanner(self.llm, self.memory_manager, self.shared_state, self.prompt_logger)
        self.task_handler = TaskHandler(self.llm, self.task_stack_manager, self.task_planner, self.memory_manager, self.prompt_logger)

        # Heart & Mind Systems
        self.goal_hierarchy = GoalHierarchy(shared_state)
        self.self_awareness = SelfAwareness(shared_state, self.memory_manager)
        self.mental_state = MentalState(shared_state)
        self.contemplation = ContemplationManager(
            self.memory_manager,
            llm_model,
            self.mental_state,
            self.goal_hierarchy
        )
        
        # Initialize PromptManager 
        self.prompt_manager = PromptManager()

        self._load_persisted_state()
        
        logger.info("High-level brain initialized with refactored task stack management.")
    
    async def think(self, woken_by_event: bool = False):
        """
        Main thinking cycle for high-level brain.
        """
        if woken_by_event:
            logger.info("High-level brain: Event-driven wake (processing request)")
        else:
            logger.info("High-level brain: Periodic wake (contemplation)")
        
        try:
            # Step 1: Handle modification requests
            mod_request = await self.shared_state.get('modification_request')
            if mod_request and not mod_request.get('processed', False):
                logger.info("⚠️ Processing modification request from mid-level")
                response = await self._route_modification_request(mod_request)
                await self.shared_state.update('modification_response', response)
                mod_request['processed'] = True
                await self.shared_state.update('modification_request', mod_request)
                self.mental_state.update_mood(stress=min(1.0, self.mental_state.mood['stress'] + 0.1))
                logger.info("✅ Modification request processed")
                return

            # Step 2: Ensure there is an active task available
            await self._ensure_active_task()

            await self.task_stack_manager.sync_to_shared_state()

            active_task = self.task_stack_manager.get_active_task()
            if active_task:
                current_idx = active_task.get('current_step_index', 0)
                total_steps = len(active_task.get('steps', []))
                logger.info(
                    "Task stack top: %s (source=%s) - Step %s/%s",
                    active_task.get('goal', 'Unknown'),
                    active_task.get('source', 'internal'),
                    current_idx + 1 if total_steps else 0,
                    total_steps
                )
            else:
                logger.info("Task stack empty - waiting for new objectives")

            # Step 3: Contemplation during periodic wake (no interruption mechanism)
            if not woken_by_event:
                await self._idle_think()
            
            # Step 4: Periodically save mind state
            await self._save_persisted_state()
            
        except Exception as e:
            logger.error(f"Error in high-level thinking cycle: {e}", exc_info=True)
        
        logger.info("High-level brain: Thinking cycle complete")
    
    async def _generate_strategic_plan(self) -> Dict[str, Any]:
        """
        Generate strategic plan using LLM.
        """
        logger.debug("Generating strategic plan with LLM...")
        state = await self.shared_state.get_all()
        agent_name = await self.self_awareness.get_name()
        
        # Use PromptManager to render the planning prompt (v2.0 - config-driven)
        prompt = await self.prompt_manager.render(
            'high_level/planning.txt',
            context={
                'state': state,
                'agent_name': agent_name,
                'memory_manager': self.memory_manager,
                'task_stack_manager': self.task_stack_manager,
                'self_awareness': self.self_awareness,
            }
        )

        try:
            # Log prompt before sending
            prompt_file = self.prompt_logger.log_prompt(
                prompt=prompt,
                brain_layer="high",
                prompt_type="strategic_planning",
                metadata={
                    "agent_name": agent_name,
                    "current_goal": state.get('strategic_goal', 'N/A')
                }
            )
            logger.debug(f"Prompt saved to: {prompt_file}")
            
            response = await self.llm.send_request([], prompt)
            
            # Update with response
            self.prompt_logger.update_response(prompt_file, response)
            
            plan = self.task_planner._parse_llm_json(response)
            logger.info(f"Strategic plan: {plan.get('goal', 'N/A')}")
            return plan or {}
        except Exception as e:
            logger.error(f"Error generating strategic plan: {e}", exc_info=True)
            raise ValueError("Failed to generate strategic plan") from e

    async def _route_modification_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch modification requests to the TaskHandler."""
        request_type = request.get('request_type', 'stuck_task')
        if request_type == 'player_directive':
            return await self.task_handler.handle_player_directive(request)
        if request_type == 'stuck_task':
            return await self.task_handler.handle_stuck_task(request)
        
        logger.warning("Unknown modification request type: %s", request_type)
        return {'decision': 'no_change', 'explanation': f"Unknown request type '{request_type}'"}

    async def _ensure_active_task(self):
        """Ensure there is an active task available for execution."""
        if not self.task_stack_manager.get_active_task():
            strategic_plan = await self._generate_strategic_plan()
            await self.shared_state.update('strategic_goal', strategic_plan)
            goal = strategic_plan.get('goal')
            if goal and goal != 'None':
                new_plan = await self.task_planner.decompose_goal_to_steps(
                    goal=goal,
                    strategic_guidance=strategic_plan.get('strategic_guidance', ''),
                    source='internal',
                    player_name=None
                )
                if new_plan:
                    await self.task_stack_manager.push_task_plan(new_plan)
            else:
                await self.task_stack_manager._update_shared_state_with_active_task()
    
    async def _idle_think(self):
        """Idle contemplation during periodic wake."""
        try:
            await self.contemplation.contemplate()
        except Exception as e:
            logger.error(f"Error during idle contemplation: {e}", exc_info=True)
    
    def _load_persisted_state(self):
        """Load persisted mind state from disk using MindStateManager."""
        try:
            data = self.mind_state_manager.load_mind_state()
            
            if data:
                if 'goal_hierarchy' in data: 
                    self.goal_hierarchy.from_dict(data['goal_hierarchy'])
                if 'self_awareness' in data: 
                    self.self_awareness.from_dict(data['self_awareness'])
                if 'mental_state' in data: 
                    self.mental_state.from_dict(data['mental_state'])
                
                task_stack = data.get('task_stack', [])
                self.task_stack_manager.load_from_persistence(task_stack)
                
                asyncio.create_task(self.task_stack_manager.sync_to_shared_state())
                
                # Restore strategic_goal to SharedState
                if 'strategic_goal' in data:
                    asyncio.create_task(self.shared_state.update('strategic_goal', data['strategic_goal']))
                
                logger.info("Loaded persisted mind state")
            else:
                logger.info("No mind_state.json found - initializing with default state")
                # Schedule async save in the event loop
                asyncio.create_task(self._save_persisted_state())
        except Exception as e:
            logger.error(f"Failed to load mind state: {e}")
    
    async def _save_persisted_state(self):
        """Save mind state to disk using MindStateManager."""
        try:
            # Get strategic_goal from SharedState
            strategic_goal = await self.shared_state.get('strategic_goal')
            
            data = {
                'goal_hierarchy': self.goal_hierarchy.to_dict(),
                'self_awareness': self.self_awareness.to_dict(),
                'mental_state': self.mental_state.to_dict(),
                'task_stack': self.task_stack_manager.get_task_stack(),
                'strategic_goal': strategic_goal,  # Save strategic_goal
            }
            self.mind_state_manager.save_mind_state(data)
            logger.debug("Saved mind state to disk")
        except Exception as e:
            logger.error(f"Failed to save mind state: {e}")
    
    async def get_mind_context_for_prompt(self) -> str:
        """Get complete mind context for LLM prompts."""
        context = ""
        context += await self.self_awareness.get_full_context()
        context += self.goal_hierarchy.get_context_for_prompt()
        mental_context = self.mental_state.get_context_for_prompt()
        if mental_context:
            context += mental_context
        return context
    
    async def save_state(self):
        """Public method to save all brain state."""
        logger.info("Saving high-level brain state...")
        await self._save_persisted_state()
        self.memory_manager._save_json(
            self.memory_manager.players_file,
            self.memory_manager.players
        )
        logger.info("High-level brain state saved")

    # Methods to be called by mid-level brain
    async def update_active_task_step(self, step_index: int, status: str, failure_reason: Optional[str] = None):
        await self.task_stack_manager.update_active_task_step(step_index, status, failure_reason)

    async def mark_step_completed(self, step_index: int):
        await self.task_stack_manager.mark_step_completed(step_index)