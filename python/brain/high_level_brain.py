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
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
import os
from utils.memory_manager import MemoryManager
from brain.goal_hierarchy import GoalHierarchy
from brain.self_awareness import SelfAwareness
from brain.mental_state import MentalState
from brain.contemplation import ContemplationManager

logger = logging.getLogger(__name__)

class HighLevelBrain:
    """
    High-level brain for strategic thinking
    
    Runs asynchronously every 5 minutes to:
    - Receive and analyze summaries from mid-level brain
    - Update strategic goals based on experiences
    - Provide guidance when tasks fail repeatedly
    """
    
    def __init__(self, shared_state, config, llm_model, wake_event=None):
        """
        Initialize high-level brain
        
        Args:
            shared_state: Shared state object
            config: Configuration object
            llm_model: LLM model instance (Qwen by default)
            wake_event: asyncio.Event for interrupt mechanism (optional)
        """
        self.shared_state = shared_state
        self.config = config
        self.llm = llm_model
        self.last_think_time = None
        self.wake_event = wake_event  # For interrupting contemplation
        
        # Memory manager for persistence (shared with mid-level brain)
        agent_name = config.get('agent_name', 'BrainyBot')
        self.memory_manager = MemoryManager(agent_name)
        
        # In-memory cache
        self.memory = ""
        
        # Task Plan Management (completely managed by high-level brain)
        self.task_plan = {
            'goal': '',
            'steps': [],
            'current_step_index': -1,  # -1 means no active plan
            'status': 'idle'  # idle, active, paused, completed
        }
        
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
        
        # Interruptible contemplation mechanism
        self.contemplation_task = None  # Current contemplation task (can be cancelled)
        self.interrupted_contemplation = None  # Temp storage for interrupted contemplation
        
        # Load system prompt
        self.system_prompt = self._load_system_prompt()
        
        # Load persisted state if exists
        self._load_persisted_state()
        
        logger.info("High-level brain initialized with Qwen model and mind systems")
    
    def _load_system_prompt(self) -> str:
        """
        Load system prompt from file
        
        Returns:
            System prompt string
        """
        prompt_file = self.config.get('high_level_brain', {}).get('system_prompt_file')
        if not prompt_file:
            logger.warning("No system prompt file specified, using default")
            return "You are a strategic planning AI for a Minecraft agent."
        
        try:
            # Handle relative paths
            import os
            if not os.path.isabs(prompt_file):
                # Relative to project root
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                prompt_file = os.path.join(project_root, prompt_file)
            
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt = f.read()
            logger.info(f"Loaded system prompt from {prompt_file}")
            return prompt
        except Exception as e:
            logger.error(f"Failed to load system prompt: {e}")
            return "You are a strategic planning AI for a Minecraft agent."
    
    async def think(self, woken_by_event: bool = False):
        """
        Main thinking cycle for high-level brain
        
        Args:
            woken_by_event: True if woken by mid-level request, False if periodic wake
        
        Dual mechanism:
        1. Event-driven wake: Process modification requests immediately
        2. Periodic wake (every 15 min): Check if idle, contemplate if free
        
        Process:
        - Always check and handle modification requests (highest priority)
        - Update task plans if needed
        - Contemplate only during periodic wake AND if not busy
        """
        if woken_by_event:
            logger.info("High-level brain: Event-driven wake (processing request)")
        else:
            logger.info("High-level brain: Periodic wake (contemplation check)")
        
        self.last_think_time = datetime.now()
        
        try:
            # Step 1: Handle modification requests (ALWAYS CHECK - highest priority)
            mod_request = await self.shared_state.get('modification_request')
            if mod_request and not mod_request.get('processed', False):
                logger.info("⚠️ Processing modification request from mid-level")
                
                # Interrupt contemplation if running
                await self._interrupt_contemplation()
                
                # Process the request
                response = await self.handle_modification_request(mod_request)
                await self.shared_state.update('modification_response', response)
                
                # Mark as processed
                mod_request['processed'] = True
                await self.shared_state.update('modification_request', mod_request)
                
                # Increase stress slightly
                self.mental_state.update_mood(stress=min(1.0, self.mental_state.mood['stress'] + 0.1))
                
                logger.info("✅ Modification request processed")
                return  # Exit after handling request
            
            # Step 2: Check task plan status
            if self.task_plan.get('status') == 'idle' or self.task_plan.get('status') == 'completed':
                # Generate new strategic plan and task plan
                strategic_plan = await self._generate_strategic_plan()
                
                if strategic_plan.get('goal_priority') and strategic_plan.get('goal_priority') != 'None':
                    # Create task plan from strategic goal
                    await self.create_task_plan(
                        goal=strategic_plan.get('goal_priority', 'Survival'),
                        strategic_guidance=strategic_plan.get('strategic_guidance', '')
                    )
                
                await self.shared_state.update('strategic_goal', strategic_plan)
                logger.info(f"Strategic plan generated: {strategic_plan.get('goal_priority', 'N/A')}")
            else:
                logger.info(f"Task plan active: {self.task_plan.get('goal')} - Step {self.task_plan.get('current_step_index', 0) + 1}/{len(self.task_plan.get('steps', []))}")
            
            # Step 3: Idle contemplation (ONLY during periodic wake, and if not busy)
            if not woken_by_event:  # Only contemplate during periodic wake
                if self._is_idle() and self.mental_state.needs_contemplation():
                    logger.info("💭 High-level is idle - beginning contemplation")
                    await self._idle_think()
                else:
                    if not self._is_idle():
                        logger.info("⏭️ High-level is busy - skipping contemplation this cycle")
                    else:
                        logger.debug("Contemplation not needed this cycle")
            
            # Step 4: Periodically save mind state
            self._save_persisted_state()
            
        except Exception as e:
            logger.error(f"Error in high-level thinking cycle: {e}", exc_info=True)
        
        logger.info("High-level brain: Thinking cycle complete")
    
    def format_memory_for_prompt(self) -> str:
        """
        Format memory into a readable string for prompts
        
        Returns:
            Formatted memory string
        """
        if not self.memory:
            return "No memory yet."
        return self.memory.strip()
    
    def get_learned_experience_base(self) -> str:
        """
        Get accumulated learned experience from persistent storage
        
        Returns:
            Learned experience string for prompts
        """
        # Use memory manager's learned experience summary
        learned_exp = self.memory_manager.get_learned_experience_summary(
            max_insights=5,
            max_lessons=10
        )
        
        # Add player information
        players_info = self.memory_manager.get_all_players_summary()
        if players_info and players_info != "No players known yet.":
            learned_exp += "\n\n" + players_info
        
        return learned_exp if learned_exp else "No learned experience yet."
    
    async def _generate_strategic_plan(self) -> Dict[str, Any]:
        """
        Generate strategic plan using LLM
        
        Returns:
            Strategic plan dictionary
        """
        logger.debug("Generating strategic plan with LLM...")
        
        # Get current game state
        state = await self.shared_state.get_all()
        position = state.get('position', {})
        health = state.get('health', 20)
        food = state.get('food', 20)
        inventory = state.get('inventory', {})
        
        # Agent age (since first spawn, persists across sessions)
        agent_age_days = state.get('agent_age_days', 0)
        agent_age_ticks = state.get('agent_age_ticks', 0)
        
        # World time (since world creation)
        world_day = state.get('world_day', 0)
        
        # Prepare prompt with placeholders replaced
        prompt = self.system_prompt
        agent_name = await self.self_awareness.get_name()  # Get name from shared state
        prompt = prompt.replace('$NAME', agent_name)
        prompt = prompt.replace('$TIMESTAMP', datetime.now().isoformat())
        prompt = prompt.replace('$BIOME', state.get('biome', 'unknown'))
        prompt = prompt.replace('$TIME_OF_DAY', str(state.get('time_of_day', 0)))
        prompt = prompt.replace('$HEALTH', str(health))
        prompt = prompt.replace('$FOOD', str(food))
        prompt = prompt.replace('$POSITION', f"x:{position.get('x', 0)}, y:{position.get('y', 0)}, z:{position.get('z', 0)}")
        
        # Agent age info (cumulative playtime, self-awareness)
        prompt = prompt.replace('$AGENT_AGE', f"{agent_age_days} game days ({agent_age_ticks} total ticks played)")
        prompt = prompt.replace('$WORLD_DAY', f"Current world day {world_day}")
        
        # Add mind context (identity, goals, mental state)
        mind_context = await self.get_mind_context_for_prompt()
        prompt = prompt.replace('$MIND_CONTEXT', mind_context)
        
        # Add learned experience base (memory + insights + lessons)
        learned_exp = self.get_learned_experience_base()
        prompt = prompt.replace('$KNOWLEDGE', learned_exp)
        prompt = prompt.replace('$LEARNED_EXPERIENCE', learned_exp)
        
        # Add current task plan
        task_plan_text = self._format_task_plan_for_prompt()
        prompt = prompt.replace('$TASK_PLAN', task_plan_text)
        
        # Add memory and player info
        prompt = prompt.replace('$MEMORY', self.format_memory_for_prompt())
        players_info = self.memory_manager.get_all_players_summary()
        prompt = prompt.replace('$PLAYERS_INFO', players_info)
        
        # Deprecated placeholder
        prompt = prompt.replace('$RECENT_EXPERIENCES', '')  # Deprecated: experience_history removed
        
        # Current goals
        strategic_goal = state.get('strategic_goal') or {}
        current_goal = strategic_goal.get('goal_priority', 'None')
        prompt = prompt.replace('$CURRENT_GOALS', current_goal)
        
        # Inventory summary
        inv_summary = ", ".join([f"{k}: {v}" for k, v in list(inventory.items())[:5]])
        if not inv_summary:
            inv_summary = "Empty"
        prompt = prompt.replace('$INVENTORY_SUMMARY', inv_summary)
        
        # Call LLM
        try:
            response = await self.llm.send_request([], prompt)
            
            # Try to parse JSON response
            # Find JSON in response (between ```json and ```)
            if '```json' in response:
                json_start = response.find('```json') + 7
                json_end = response.find('```', json_start)
                json_str = response[json_start:json_end].strip()
            elif '{' in response:
                # Find JSON object
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                json_str = response[json_start:json_end]
            else:
                json_str = response
            
            plan = json.loads(json_str)
            logger.info(f"Strategic plan: {plan.get('goal_priority', 'N/A')}")
            
            # Apply player relationship updates if provided
            if 'player_relationship_updates' in plan and plan['player_relationship_updates']:
                for update in plan['player_relationship_updates']:
                    try:
                        player_name = update.get('player_name')
                        trust_delta = update.get('trust_delta', 0.0)
                        new_relationship = update.get('new_relationship')
                        reason = update.get('reason', '')
                        
                        if not player_name:
                            continue
                        
                        # Ensure player exists in memory
                        player_data = self.memory_manager.get_player_data(player_name)
                        if not player_data:
                            # Initialize player data if first time
                            self.memory_manager.update_player_info(player_name, 'interaction', 'first analysis')
                            player_data = self.memory_manager.get_player_data(player_name)
                        
                        # Apply trust level change
                        if trust_delta != 0.0 and player_data:
                            old_trust = player_data.get('trust_level', 0.5)
                            new_trust = max(0.0, min(1.0, old_trust + trust_delta))
                            self.memory_manager.players[player_name]['trust_level'] = new_trust
                            logger.info(f"👥 Trust with {player_name}: {old_trust:.2f} → {new_trust:.2f} (Δ{trust_delta:+.2f})")
                        
                        # Apply relationship status change
                        if new_relationship and new_relationship in ['neutral', 'friendly', 'hostile']:
                            old_rel = player_data.get('relationship', 'neutral')
                            if old_rel != new_relationship:
                                self.memory_manager.players[player_name]['relationship'] = new_relationship
                                logger.info(f"👥 Relationship with {player_name}: {old_rel} → {new_relationship}")
                        
                        # Log reason
                        if reason:
                            logger.info(f"💭 Reason: {reason}")
                        
                        # Save changes
                        self.memory_manager._save_json(self.memory_manager.players_file, self.memory_manager.players)
                    
                    except Exception as e:
                        logger.error(f"Error applying player relationship update: {e}")
            
            return plan
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response was: {response}")
            # Return default plan
            return {
                'goal_priority': 'survival',
                'risk_level': 'medium',
                'critical_needs': ['food', 'shelter'],
                'strategic_guidance': 'Focus on basic survival - gather resources and build shelter.',
                'reasoning': 'Failed to parse LLM response, using default plan'
            }
        except Exception as e:
            logger.error(f"Error generating strategic plan: {e}", exc_info=True)
            return {
                'goal_priority': 'survival',
                'risk_level': 'unknown',
                'critical_needs': [],
                'strategic_guidance': 'Error occurred, focus on survival.',
                'reasoning': str(e)
            }
    
    async def get_memory_context(self) -> str:
        """
        Get current memory context
        
        Returns:
            String containing current memory
        """
        return self.memory
    
    # ===== TASK PLAN MANAGEMENT =====
    
    async def create_task_plan(self, goal: str, strategic_guidance: str = "") -> Dict[str, Any]:
        """
        Create a new task plan from high-level goal
        
        Args:
            goal: High-level goal description
            strategic_guidance: Additional strategic context
        
        Returns:
            Task plan dictionary
        """
        logger.info(f"Creating task plan for goal: {goal}")
        
        # Get current state for context
        state = await self.shared_state.get_all()
        
        # Use LLM to decompose goal into steps
        prompt = f"""Create a detailed step-by-step plan to achieve this goal in Minecraft.

Goal: {goal}
Strategic Guidance: {strategic_guidance or 'None'}

Current Context:
- Health: {state.get('health', 20)}/20
- Food: {state.get('food', 20)}/20
- Inventory: {', '.join(list(state.get('inventory', {}).keys())[:10]) or 'Empty'}

Respond with a JSON object containing:
{{
  "steps": [
    {{"id": 1, "description": "step description", "status": "pending"}},
    {{"id": 2, "description": "next step", "status": "pending"}}
  ]
}}

Be specific and practical. Each step should be achievable in Minecraft.
Limit to 5-10 steps. Do not number the descriptions.

Response (JSON only):"""
        
        try:
            response = await self.llm.send_request([], prompt)
            
            # Extract JSON
            if '```json' in response:
                json_start = response.find('```json') + 7
                json_end = response.find('```', json_start)
                json_str = response[json_start:json_end].strip()
            elif '{' in response:
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                json_str = response[json_start:json_end]
            else:
                raise ValueError("No JSON found in response")
            
            plan_data = json.loads(json_str)
            steps = plan_data.get('steps', [])
            
            # Create task plan
            self.task_plan = {
                'goal': goal,
                'steps': steps,
                'current_step_index': 0 if steps else -1,
                'status': 'active' if steps else 'idle',
                'strategic_guidance': strategic_guidance
            }
            
            # Publish to shared state for mid-level brain
            await self.shared_state.update('task_plan', self.task_plan)
            
            logger.info(f"Created task plan with {len(steps)} steps")
            return self.task_plan
        
        except Exception as e:
            logger.error(f"Error creating task plan: {e}", exc_info=True)
            return {'goal': goal, 'steps': [], 'current_step_index': -1, 'status': 'error'}
    
    async def handle_modification_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle task plan modification request from mid-level brain
        
        Args:
            request: {
                'type': 'modify_step' | 'add_step' | 'remove_step' | 'change_approach',
                'reason': 'why modification is needed',
                'current_step_index': int,
                'suggestion': 'suggested modification',
                'failures': ['list of failures'],
                'context': 'additional context',
                'player_name': 'player who requested (if from chat)'
            }
        
        Returns:
            Response: {
                'decision': 'approve' | 'reject' | 'revise',
                'explanation': 'why this decision',
                'updated_plan': {...} if approved,
                'guidance': 'how to proceed'
            }
        """
        logger.info(f"Received modification request: {request.get('type')}")
        
        req_type = request.get('type', 'unknown')
        reason = request.get('reason', 'No reason provided')
        current_step_idx = request.get('current_step_index', -1)
        suggestion = request.get('suggestion', '')
        failures = request.get('failures', [])
        player_name = request.get('player_name', None)
        
        # Get player relationship if this is a player request
        player_context = ""
        if player_name:
            try:
                # Get player info from memory
                player_info = self.memory_manager.get_player_data(player_name)
                if player_info:
                    relationship = player_info.get('relationship', 'neutral')
                    interactions = len(player_info.get('interactions', []))
                    trust = player_info.get('trust_level', 0.5)
                    personality = player_info.get('personality', [])
                    preferences = player_info.get('preferences', [])
                    first_met = player_info.get('first_met', 'Unknown')
                    
                    # Build context description without explicit instructions
                    personality_str = ", ".join(personality[-3:]) if personality else "unknown"
                    preferences_str = ", ".join(preferences[-3:]) if preferences else "unknown"
                    
                    player_context = f"""
PLAYER INFORMATION:
This request comes from player: {player_name}
- First met: {first_met}
- You've had {interactions} interactions with them
- Their personality traits you've observed: {personality_str}
- Their preferences: {preferences_str}
- Current relationship status: {relationship}
- Your trust in them: {trust:.2f} (scale 0.0-1.0)
"""
                else:
                    player_context = f"""
PLAYER INFORMATION:
This request comes from player: {player_name}
- This is your first interaction with them
- No prior relationship history
"""
            except Exception as e:
                logger.warning(f"Could not get player info for {player_name}: {e}")
                player_context = f"""
PLAYER INFORMATION:
This request comes from player: {player_name}
- Relationship information unavailable
"""
        
        # Build prompt for LLM to decide
        current_plan_text = self._format_task_plan_for_prompt()
        
        prompt = f"""You are a strategic planner. The tactical executor (mid-level brain) requests to modify the task plan.

CURRENT TASK PLAN:
{current_plan_text}

MODIFICATION REQUEST:
Type: {req_type}
Reason: {reason}
Current Step: {current_step_idx + 1} of {len(self.task_plan.get('steps', []))}
Suggestion: {suggestion}
Recent Failures: {', '.join(failures[:3]) if failures else 'None'}
{player_context}
Your options:
1. APPROVE: Accept the modification request
2. REJECT: Reject and provide alternative guidance to overcome the difficulty
3. REVISE: Propose a better modification

Respond with JSON:
{{
  "decision": "approve|reject|revise",
  "explanation": "brief explanation",
  "guidance": "how mid-level should proceed (if reject)",
  "revised_suggestion": "better modification (if revise)"
}}

Consider:
- Is the difficulty truly insurmountable, or can it be overcome with better approach?
- Be strategic - sometimes pushing through difficulty leads to learning.
- If this is a player request, you have the autonomy to decide based on the information provided.

Response (JSON only):"""
        
        try:
            response = await self.llm.send_request([], prompt)
            
            # Extract JSON
            if '```json' in response:
                json_start = response.find('```json') + 7
                json_end = response.find('```', json_start)
                json_str = response[json_start:json_end].strip()
            elif '{' in response:
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                json_str = response[json_start:json_end]
            else:
                raise ValueError("No JSON in response")
            
            decision_data = json.loads(json_str)
            decision = decision_data.get('decision', 'reject')
            explanation = decision_data.get('explanation', '')
            guidance = decision_data.get('guidance', '')
            revised_suggestion = decision_data.get('revised_suggestion', '')
            
            logger.info(f"Decision: {decision} - {explanation}")
            
            # Apply modification if approved or revised
            updated_plan = None
            if decision == 'approve':
                updated_plan = await self._apply_modification(req_type, current_step_idx, suggestion)
            elif decision == 'revise' and revised_suggestion:
                updated_plan = await self._apply_modification(req_type, current_step_idx, revised_suggestion)
            
            return {
                'decision': decision,
                'explanation': explanation,
                'updated_plan': updated_plan,
                'guidance': guidance or revised_suggestion or explanation
            }
        
        except Exception as e:
            logger.error(f"Error handling modification request: {e}", exc_info=True)
            return {
                'decision': 'reject',
                'explanation': f'Error processing request: {str(e)}',
                'guidance': 'Please retry the current step.'
            }
    
    async def _apply_modification(self, mod_type: str, step_index: int, modification: str) -> Dict[str, Any]:
        """
        Apply approved modification to task plan
        
        Args:
            mod_type: Type of modification
            step_index: Index of step to modify
            modification: Modification description
        
        Returns:
            Updated task plan
        """
        steps = self.task_plan.get('steps', [])
        
        if mod_type == 'modify_step':
            if 0 <= step_index < len(steps):
                steps[step_index]['description'] = modification
                steps[step_index]['status'] = 'pending'  # Reset status
                logger.info(f"Modified step {step_index + 1}: {modification}")
        
        elif mod_type == 'add_step':
            new_step = {
                'id': len(steps) + 1,
                'description': modification,
                'status': 'pending'
            }
            # Insert after current step
            steps.insert(step_index + 1, new_step)
            logger.info(f"Added new step after {step_index + 1}: {modification}")
        
        elif mod_type == 'remove_step':
            if 0 <= step_index < len(steps):
                removed = steps.pop(step_index)
                logger.info(f"Removed step {step_index + 1}: {removed['description']}")
        
        elif mod_type == 'change_approach':
            # Completely revise remaining steps
            # Keep completed steps, replace remaining
            completed_steps = [s for s in steps[:step_index] if s.get('status') == 'completed']
            # Parse new steps from modification
            # For now, just add as single step
            new_step = {
                'id': len(completed_steps) + 1,
                'description': modification,
                'status': 'pending'
            }
            steps = completed_steps + [new_step]
            self.task_plan['current_step_index'] = len(completed_steps)
            logger.info(f"Changed approach: {modification}")
        
        # Update task plan
        self.task_plan['steps'] = steps
        
        # Re-number step IDs
        for i, step in enumerate(steps):
            step['id'] = i + 1
        
        # Publish to shared state
        await self.shared_state.update('task_plan', self.task_plan)
        
        return self.task_plan
    
    async def mark_step_completed(self, step_index: int):
        """
        Mark a step as completed and move to next
        
        Args:
            step_index: Index of completed step
        """
        steps = self.task_plan.get('steps', [])
        
        if 0 <= step_index < len(steps):
            steps[step_index]['status'] = 'completed'
            self.task_plan['current_step_index'] = step_index + 1
            
            # Check if all steps completed
            if step_index + 1 >= len(steps):
                self.task_plan['status'] = 'completed'
                logger.info(f"Task plan completed! Goal: {self.task_plan.get('goal')}")
            
            await self.shared_state.update('task_plan', self.task_plan)
            logger.info(f"Step {step_index + 1} marked completed")
    
    async def mark_step_failed(self, step_index: int, reason: str = ""):
        """
        Mark a step as failed
        
        Args:
            step_index: Index of failed step
            reason: Failure reason
        """
        steps = self.task_plan.get('steps', [])
        
        if 0 <= step_index < len(steps):
            steps[step_index]['status'] = 'failed'
            steps[step_index]['failure_reason'] = reason
            
            await self.shared_state.update('task_plan', self.task_plan)
            logger.warning(f"Step {step_index + 1} marked failed: {reason}")
    
    def _format_task_plan_for_prompt(self) -> str:
        """
        Format task plan for LLM prompts
        
        Returns:
            Formatted string
        """
        if not self.task_plan.get('steps'):
            return "No active task plan"
        
        goal = self.task_plan.get('goal', 'Unknown')
        current_idx = self.task_plan.get('current_step_index', 0)
        steps = self.task_plan.get('steps', [])
        
        lines = [f"Goal: {goal}", f"Progress: Step {current_idx + 1}/{len(steps)}", ""]
        
        for i, step in enumerate(steps):
            status = step.get('status', 'pending')
            marker = '✓' if status == 'completed' else ('✗' if status == 'failed' else ('→' if i == current_idx else '○'))
            lines.append(f"{marker} Step {i + 1}: {step['description']} [{status}]")
        
        return "\n".join(lines)
    
    # ==================== Mind & Heart Systems ====================
    
    async def _interrupt_contemplation(self):
        """
        Interrupt current contemplation if active
        
        Saves the current contemplation progress to temp (in memory).
        Called when mid-level sends urgent modification request.
        """
        if self.contemplation_task and not self.contemplation_task.done():
            logger.info("🛑 Interrupting active contemplation...")
            
            # Get current contemplation progress from contemplation manager
            progress = self.contemplation.get_current_progress()
            
            if progress:
                # Save to temp (in memory only)
                self.interrupted_contemplation = {
                    'mode': progress.get('mode', 'unknown'),
                    'context': progress.get('context'),
                    'progress': progress.get('progress'),
                    'interrupted_at': datetime.now().isoformat()
                }
                logger.info(f"💾 Saved interrupted contemplation to temp: {self.interrupted_contemplation['mode']}")
            
            # Cancel the task
            self.contemplation_task.cancel()
            
            try:
                await self.contemplation_task
            except asyncio.CancelledError:
                logger.info("✅ Contemplation task cancelled successfully")
            
            self.contemplation_task = None
    
    async def _resume_contemplation(self):
        """
        Resume interrupted contemplation from temp
        
        If there was an interrupted contemplation, resume it.
        Otherwise, do nothing.
        """
        if self.interrupted_contemplation:
            logger.info(f"🔄 Resuming interrupted contemplation: {self.interrupted_contemplation['mode']}")
            
            try:
                # Resume from saved progress
                await self.contemplation.resume_from_temp(self.interrupted_contemplation)
                
                # Clear temp after successful resume
                logger.info("✅ Resumed contemplation completed")
                self.interrupted_contemplation = None
                
            except Exception as e:
                logger.error(f"Error resuming contemplation: {e}", exc_info=True)
                # Clear temp even if failed
                self.interrupted_contemplation = None
    
    def _is_idle(self) -> bool:
        """
        Check if high-level brain is idle (not busy with tasks)
        
        Returns:
            True if idle (can contemplate), False if busy
        """
        # Check if there's an active task plan being executed
        if self.task_plan.get('status') == 'active':
            # Task plan is active - high-level is busy monitoring
            return False
        
        # Check if waiting for mid-level response
        # (This shouldn't happen in normal flow, but check anyway)
        
        # Otherwise, consider idle
        return True
    
    async def _idle_think(self):
        """
        Idle contemplation when not busy
        
        This is where the agent's "mind" wanders and processes internal thoughts.
        Called during periodic wake cycles (every 15 minutes) if high-level is idle.
        
        Runs as an interruptible task - can be cancelled if mid-level sends urgent request.
        Uses asyncio.wait() to simultaneously wait for contemplation OR wake event.
        """
        # Step 1: Check if there's interrupted contemplation to resume
        if self.interrupted_contemplation:
            try:
                interrupted_time = datetime.fromisoformat(
                    self.interrupted_contemplation['interrupted_at']
                )
                age_minutes = (datetime.now() - interrupted_time).total_seconds() / 60
                
                if age_minutes < 300:  # Resume if within 300 minutes
                    logger.info(f"🔄 Resuming interrupted contemplation ({age_minutes:.1f} minutes ago)")
                    await self._resume_contemplation()
                    return  # Resume completed, exit
                else:
                    logger.info(f"🗑️ Clearing expired contemplation temp ({age_minutes:.1f} minutes ago)")
                    self.interrupted_contemplation = None
                    # Continue to start new contemplation
            except Exception as e:
                logger.error(f"Error checking interrupted contemplation: {e}")
                self.interrupted_contemplation = None
        
        # Step 2: Check if contemplation is appropriate
        # Check if high-level brain is busy handling mid-level requests
        if await self.mental_state.is_busy():
            logger.debug("Mental state busy - processing mid-level request")
            return
        
        # Step 3: Perform contemplation as an interruptible task
        try:
            # Create contemplation task
            contemplation_task = asyncio.create_task(
                self.contemplation.contemplate()
            )
            self.contemplation_task = contemplation_task
            
            # If wake_event is available, wait for contemplation OR wake event
            if self.wake_event:
                # Create a task that waits for wake event
                wake_task = asyncio.create_task(self.wake_event.wait())
                
                # Wait for FIRST to complete: contemplation or wake event
                done, pending = await asyncio.wait(
                    {contemplation_task, wake_task},
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # Check which completed first
                if contemplation_task in done:
                    # Contemplation completed normally
                    result = await contemplation_task
                    if result:
                        logger.info("💭 Idle contemplation completed")
                else:
                    # Wake event triggered - contemplation interrupted
                    logger.info("🛑 Contemplation interrupted by wake event (urgent request)")
                    
                    # Save progress before cancellation
                    progress = self.contemplation.get_current_progress()
                    if progress:
                        self.interrupted_contemplation = {
                            'mode': progress.get('mode', 'unknown'),
                            'context': progress.get('context'),
                            'progress': progress.get('progress'),
                            'interrupted_at': datetime.now().isoformat()
                        }
                        logger.info(f"� Saved contemplation progress to temp: {self.interrupted_contemplation['mode']}")
            
            else:
                # No wake_event - simple wait (backwards compatibility)
                contemplated = await contemplation_task
                
                if contemplated:
                    logger.info("💭 Idle contemplation completed")
            
            # Clear task reference
            self.contemplation_task = None
        
        except asyncio.CancelledError:
            logger.info("💭 Contemplation was cancelled")
            self.contemplation_task = None
            # Don't re-raise - this is expected behavior
        
        except Exception as e:
            logger.error(f"Error during idle contemplation: {e}", exc_info=True)
            self.contemplation_task = None
    
    def _load_persisted_state(self):
        """Load persisted mind state from disk"""
        try:
            # Use memory manager's base directory
            state_file = os.path.join(
                self.memory_manager.base_dir,
                'mind_state.json'
            )
            
            if os.path.exists(state_file):
                with open(state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Load each system
                if 'goal_hierarchy' in data:
                    self.goal_hierarchy.from_dict(data['goal_hierarchy'])
                if 'self_awareness' in data:
                    self.self_awareness.from_dict(data['self_awareness'])
                if 'mental_state' in data:
                    self.mental_state.from_dict(data['mental_state'])
                
                logger.info("Loaded persisted mind state")
        
        except Exception as e:
            logger.error(f"Failed to load mind state: {e}")
    
    def _save_persisted_state(self):
        """Save mind state to disk"""
        try:
            state_file = os.path.join(
                self.memory_manager.base_dir,
                'mind_state.json'
            )
            
            data = {
                'goal_hierarchy': self.goal_hierarchy.to_dict(),
                'self_awareness': self.self_awareness.to_dict(),
                'mental_state': self.mental_state.to_dict(),
                'saved_at': datetime.now().isoformat()
            }
            
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.debug("Saved mind state to disk")
        
        except Exception as e:
            logger.error(f"Failed to save mind state: {e}")
    
    async def get_mind_context_for_prompt(self) -> str:
        """
        Get complete mind context for LLM prompts
        
        Returns:
            Formatted context string including identity, goals, mental state
        """
        context = ""
        
        # Identity and self-awareness
        context += await self.self_awareness.get_full_context()
        
        # Goal hierarchy
        context += self.goal_hierarchy.get_context_for_prompt()
        
        # Mental state (if relevant)
        mental_context = self.mental_state.get_context_for_prompt()
        if mental_context:
            context += mental_context
        
        return context
    
    async def save_state(self):
        """Public method to save all brain state"""
        logger.info("Saving high-level brain state...")
        self._save_persisted_state()
        # Memory manager auto-saves, but force save here for safety
        self.memory_manager._save_json(
            self.memory_manager.players_file,
            self.memory_manager.players
        )
        logger.info("High-level brain state saved")
