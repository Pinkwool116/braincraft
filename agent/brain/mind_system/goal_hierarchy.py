"""
Goal Hierarchy System

Manages hierarchical goals: life vision → long-term goals → task plans
Uses milestones instead of numeric progress tracking
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class GoalHierarchy:
    """
    Three-level goal hierarchy with milestone tracking
    
    Structure:
    - Life Vision: Overarching purpose and direction
    - Long-term Goals: Major objectives (weeks/months in game time)
    - Task Plan: Specific actionable tasks (current focus)
    """
    
    def __init__(self, shared_state):
        """
        Initialize goal hierarchy
        
        Args:
            shared_state: SharedState instance for accessing game_days
        """
        self.shared_state = shared_state
        
        # Life vision (highest level)
        self.life_vision = {
            'vision': None,  # Overall purpose/direction
            'created_at_days': None,
            'last_revised_at_days': None
        }
        
        # Long-term goals (with milestone tracking)
        self.long_term_goals = []
        # Format: {
        #     'id': unique_id,
        #     'goal': description,
        #     'milestones': [milestone descriptions],
        #     'current_milestone': index,
        #     'started_at_days': game_days,
        #     'target_days': estimated_game_days,
        #     'status': 'active'/'paused'/'completed'/'abandoned',
        #     'notes': []
        # }
        
        # Current task plan (tactical level)
        self.task_plan = {
            'current_focus': None,
            'steps': [],  # List of concrete steps
            'context': None,  # Why this task
            'started_at_days': None
        }
        
        # Life events (for reflection)
        self.life_events = []
        # Format: {
        #     'day': game_days,
        #     'event': description,
        #     'significance': 'minor'/'major'/'milestone'
        # }
        
        self._next_goal_id = 1
    
    def set_life_vision(self, vision: str):
        """Set or revise life vision"""
        current_days = self.shared_state.get('agent_age_days', 0)
        
        if self.life_vision['vision']:
            logger.info(f"📜 Revising life vision: {vision}")
            self.life_vision['last_revised_at_days'] = current_days
        else:
            logger.info(f"📜 Setting life vision: {vision}")
            self.life_vision['created_at_days'] = current_days
        
        self.life_vision['vision'] = vision
        
        # Record as major life event
        self.add_life_event(
            event=f"Set life vision: {vision}",
            significance='major'
        )
    
    def add_long_term_goal(
        self, 
        goal: str, 
        milestones: List[str],
        estimated_days: Optional[int] = None
    ) -> int:
        """
        Add a new long-term goal with milestones
        
        Args:
            goal: Goal description
            milestones: List of milestone descriptions
            estimated_days: Estimated game days to complete
        
        Returns:
            Goal ID
        """
        current_days = self.shared_state.get('agent_age_days', 0)
        
        goal_id = self._next_goal_id
        self._next_goal_id += 1
        
        goal_data = {
            'id': goal_id,
            'goal': goal,
            'milestones': milestones,
            'current_milestone': 0,
            'started_at_days': current_days,
            'target_days': current_days + estimated_days if estimated_days else None,
            'status': 'active',
            'notes': []
        }
        
        self.long_term_goals.append(goal_data)
        
        logger.info(f"🎯 New long-term goal: {goal}")
        logger.info(f"   Milestones: {', '.join(milestones[:3])}...")
        
        self.add_life_event(
            event=f"Started goal: {goal}",
            significance='major'
        )
        
        return goal_id
    
    def advance_milestone(self, goal_id: int, notes: Optional[str] = None) -> bool:
        """
        Advance to next milestone in a goal
        
        Args:
            goal_id: ID of the goal
            notes: Optional notes about milestone completion
        
        Returns:
            True if advanced, False if goal completed or not found
        """
        goal = self._find_goal(goal_id)
        if not goal:
            return False
        
        current_milestone = goal['current_milestone']
        total_milestones = len(goal['milestones'])
        
        if current_milestone >= total_milestones - 1:
            # Completed!
            goal['status'] = 'completed'
            logger.info(f"✅ Goal completed: {goal['goal']}")
            
            self.add_life_event(
                event=f"Completed goal: {goal['goal']}",
                significance='milestone'
            )
            return False
        
        # Advance to next milestone
        goal['current_milestone'] += 1
        milestone_name = goal['milestones'][goal['current_milestone']]
        
        if notes:
            goal['notes'].append(f"Milestone {current_milestone}: {notes}")
        
        logger.info(f"📍 Milestone reached: {milestone_name}")
        
        self.add_life_event(
            event=f"Milestone: {milestone_name}",
            significance='minor'
        )
        
        return True
    
    def pause_goal(self, goal_id: int, reason: str):
        """Pause a long-term goal"""
        goal = self._find_goal(goal_id)
        if goal:
            goal['status'] = 'paused'
            goal['notes'].append(f"Paused: {reason}")
            logger.info(f"⏸️ Paused goal: {goal['goal']}")
    
    def resume_goal(self, goal_id: int):
        """Resume a paused goal"""
        goal = self._find_goal(goal_id)
        if goal and goal['status'] == 'paused':
            goal['status'] = 'active'
            logger.info(f"▶️ Resumed goal: {goal['goal']}")
    
    def abandon_goal(self, goal_id: int, reason: str):
        """Abandon a goal"""
        goal = self._find_goal(goal_id)
        if goal:
            goal['status'] = 'abandoned'
            goal['notes'].append(f"Abandoned: {reason}")
            logger.info(f"❌ Abandoned goal: {goal['goal']}")
    
    def set_task_plan(self, focus: str, steps: List[str], context: Optional[str] = None):
        """
        Set current task plan (tactical level)
        
        Args:
            focus: What we're trying to accomplish
            steps: Concrete steps to take
            context: Why this task (optional)
        """
        current_days = self.shared_state.get('agent_age_days', 0)
        
        self.task_plan = {
            'current_focus': focus,
            'steps': steps,
            'context': context,
            'started_at_days': current_days
        }
        
        logger.info(f"📋 Task plan: {focus}")
        logger.info(f"   Steps: {len(steps)}")
    
    def add_life_event(self, event: str, significance: str = 'minor'):
        """
        Record a life event
        
        Args:
            event: Event description
            significance: 'minor'/'major'/'milestone'
        """
        current_days = self.shared_state.get('agent_age_days', 0)
        
        self.life_events.append({
            'day': current_days,
            'event': event,
            'significance': significance
        })
        
        # Keep only recent events (last 100)
        if len(self.life_events) > 100:
            # Keep all major/milestone events, trim minor ones
            major_events = [e for e in self.life_events if e['significance'] in ['major', 'milestone']]
            recent_minor = [e for e in self.life_events if e['significance'] == 'minor'][-50:]
            self.life_events = sorted(major_events + recent_minor, key=lambda x: x['day'])
    
    def get_active_goals(self) -> List[Dict]:
        """Get all active long-term goals"""
        return [g for g in self.long_term_goals if g['status'] == 'active']
    
    def get_goal_summary(self, goal_id: int) -> Optional[str]:
        """Get human-readable summary of a goal's progress"""
        goal = self._find_goal(goal_id)
        if not goal:
            return None
        
        current = goal['current_milestone']
        total = len(goal['milestones'])
        current_milestone = goal['milestones'][current]
        
        days_elapsed = self.shared_state.get('agent_age_days', 0) - goal['started_at_days']
        
        summary = f"{goal['goal']}\n"
        summary += f"Milestone {current + 1}/{total}: {current_milestone}\n"
        summary += f"Status: {goal['status']} (Day {days_elapsed} since start)\n"
        
        if goal['target_days']:
            days_remaining = goal['target_days'] - self.shared_state.get('agent_age_days', 0)
            summary += f"Target: {days_remaining} days remaining\n"
        
        return summary
    
    def get_context_for_prompt(self) -> str:
        """Generate context string for LLM prompts"""
        context = ""
        
        # Life vision
        if self.life_vision['vision']:
            context += f"LIFE VISION: {self.life_vision['vision']}\n\n"
        
        # Active goals
        active_goals = self.get_active_goals()
        if active_goals:
            context += "ACTIVE LONG-TERM GOALS:\n"
            for goal in active_goals[:3]:  # Top 3
                current = goal['current_milestone']
                total = len(goal['milestones'])
                milestone = goal['milestones'][current]
                context += f"- {goal['goal']}\n"
                context += f"  Milestone {current + 1}/{total}: {milestone}\n"
            context += "\n"
        
        # Current task
        if self.task_plan['current_focus']:
            context += f"CURRENT TASK: {self.task_plan['current_focus']}\n"
            if self.task_plan['context']:
                context += f"Context: {self.task_plan['context']}\n"
            context += "\n"
        
        # Recent significant events
        recent_events = [e for e in self.life_events if e['significance'] != 'minor'][-5:]
        if recent_events:
            context += "RECENT MILESTONES:\n"
            for event in recent_events:
                context += f"- Day {event['day']}: {event['event']}\n"
        
        return context
    
    def _find_goal(self, goal_id: int) -> Optional[Dict]:
        """Find goal by ID"""
        for goal in self.long_term_goals:
            if goal['id'] == goal_id:
                return goal
        return None
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary for saving"""
        return {
            'life_vision': self.life_vision,
            'long_term_goals': self.long_term_goals,
            'task_plan': self.task_plan,
            'life_events': self.life_events,
            '_next_goal_id': self._next_goal_id
        }
    
    def from_dict(self, data: Dict):
        """Load from dictionary"""
        self.life_vision = data.get('life_vision', self.life_vision)
        self.long_term_goals = data.get('long_term_goals', [])
        self.task_plan = data.get('task_plan', self.task_plan)
        self.life_events = data.get('life_events', [])
        self._next_goal_id = data.get('_next_goal_id', 1)
