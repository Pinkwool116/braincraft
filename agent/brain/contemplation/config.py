"""
Contemplation Configuration

Defines settings for different types of idle contemplation.
"""

CONTEMPLATION_CONFIG = {
    # Thinking modes and their weights (for weighted random selection)
    'modes': {
        'consolidate_experiences': {
            'weight': 0.3,
            'description': 'Organize and consolidate recent experiences into patterns',
            'min_experiences': 5,  # Minimum experiences needed
            'requires_game_state': False,  # Does not need game environment
        },
        'connect_insights': {
            'weight': 0.2,
            'description': 'Find creative connections between different insights',
            'min_insights': 3,
            'requires_game_state': False,
        },
        'self_reflection_light': {
            'weight': 0.2,
            'description': 'Quick self-awareness check',
            'min_experiences': 1,
            'requires_game_state': False,
        },
        'relationship_pondering': {
            'weight': 0.15,
            'description': 'Think about relationships with players',
            'requires_relationships': True,  # Needs at least one relationship
            'requires_game_state': False,
        },
        'existential_wonder': {
            'weight': 0.1,
            'description': 'Wonder about existence and purpose',
            'min_life_events': 2,  # Needs some life experience
            'requires_game_state': False,
        },
        'creative_daydream': {
            'weight': 0.05,
            'description': 'Imagine new possibilities and scenarios',
            'requires_game_state': False,
        }
    },
    
    # Output settings
    'output': {
        'add_to_knowledge_threshold': 0.6,  # Confidence threshold to add new insight
        'max_insights_per_session': 2,      # Max new insights per contemplation
        'log_thoughts': True,                # Log thought process
        'save_to_memory': True,              # Save contemplation results
    }
}
