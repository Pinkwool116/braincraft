"""
Unified Prompt Management System

Centralized prompt loading and variable substitution with configuration-driven design.
Automatically loads variable mappings from variable_config.yaml and strictly validates
all template variables.

Key features:
- Configuration-driven: Variable mappings loaded from YAML config
- Strict validation: Undefined variables cause immediate errors
- Zero registration: No need to manually register data providers in brain components
- Centralized data logic: All data retrieval in data_providers.py
"""

import os
import re
import asyncio
import logging
import yaml
from typing import Dict, Any, Set, Callable, Optional

logger = logging.getLogger(__name__)


class PromptManager:
    """
    Unified prompt manager with configuration-driven variable resolution.
    
    Features:
    - Automatic loading of variable mappings from variable_config.yaml
    - Strict validation: Undefined variables raise ValueError
    - Regex-based variable detection: $UPPERCASE_NAME pattern
    - No manual registration needed: All mappings in config file
    - Support for both sync and async data providers
    
    Usage:
        # Initialize manager
        manager = PromptManager()
        
        # Render with context
        prompt = await manager.render(
            'high_level/planning.txt',
            context={
                'state': game_state,
                'agent_name': 'BrainyBot',
                'memory_manager': memory_mgr,
                'high_brain': self
            }
        )
    """
    
    # Variable pattern: $UPPERCASE_NAME (must start with letter or underscore)
    VARIABLE_PATTERN = re.compile(r'\$([A-Z_][A-Z0-9_]*)')
    
    def __init__(self, prompts_base_dir: Optional[str] = None):
        """
        Initialize prompt manager and load variable configuration.
        
        Args:
            prompts_base_dir: Base directory for prompt templates.
                            If None, defaults to agent/prompts/
        """
        if prompts_base_dir is None:
            # Default to agent/prompts/ directory (3 levels up from this file)
            current_file = os.path.abspath(__file__)
            agent_dir = os.path.dirname(os.path.dirname(current_file))
            prompts_base_dir = os.path.join(agent_dir, 'prompts')
        
        self.prompts_dir = prompts_base_dir
        self.templates: Dict[str, str] = {}  # Template cache
        
        # Load variable mappings from config file
        self.variable_map = self._load_variable_config()
        
        # Backward compatibility: Allow manual registration (but not needed)
        self.manual_providers: Dict[str, Callable] = {}
        
        logger.info(f"PromptManager initialized with {len(self.variable_map)} configured variables")
        logger.debug(f"Base directory: {self.prompts_dir}")
    
    def _load_variable_config(self) -> Dict[str, Callable]:
        """
        Load variable mappings from variable_config.yaml.
        
        Returns:
            Dictionary mapping variable names to provider functions
        """
        config_path = os.path.join(self.prompts_dir, 'variable_config.yaml')
        
        if not os.path.exists(config_path):
            logger.warning(f"Variable config not found: {config_path}")
            logger.warning("PromptManager will require manual provider registration")
            return {}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config:
                logger.warning("Variable config is empty")
                return {}
            
            # Import provider functions
            from .data_providers import PROVIDER_FUNCTIONS
            
            # Map variable names to functions
            variable_map = {}
            for var_name, func_name in config.items():
                if func_name in PROVIDER_FUNCTIONS:
                    variable_map[var_name] = PROVIDER_FUNCTIONS[func_name]
                else:
                    logger.warning(
                        f"Unknown function '{func_name}' for variable '{var_name}' "
                        f"(not found in PROVIDER_FUNCTIONS)"
                    )
            
            logger.info(f"Loaded {len(variable_map)} variable mappings from config")
            return variable_map
        
        except Exception as e:
            logger.error(f"Failed to load variable config: {e}", exc_info=True)
            return {}
    
    def get_available_variables(self) -> Set[str]:
        """
        Get all available variable names.
        
        Returns:
            Set of variable names (without $)
        """
        all_vars = set(self.variable_map.keys()) | set(self.manual_providers.keys())
        return all_vars
    
    def _load_template(self, template_path: str) -> str:
        """
        Load template from file with caching.
        
        Args:
            template_path: Relative path to template file (e.g. 'high_level/planning.txt')
        
        Returns:
            Template string
        
        Raises:
            FileNotFoundError: If template file not found
        """
        # Check cache first
        if template_path in self.templates:
            return self.templates[template_path]
        
        # Build absolute path
        full_path = os.path.join(self.prompts_dir, template_path)
        
        if not os.path.exists(full_path):
            raise FileNotFoundError(
                f"Prompt template not found: {full_path}\n"
                f"Template path: {template_path}\n"
                f"Base directory: {self.prompts_dir}"
            )
        
        # Load file
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # Cache the template
            self.templates[template_path] = template
            logger.debug(f"Loaded template: {template_path}")
            
            return template
        
        except Exception as e:
            logger.error(f"Failed to load template {template_path}: {e}")
            raise
    
    def _extract_variables(self, template: str) -> Set[str]:
        """
        Extract all $VARIABLE placeholders from template using regex.
        
        Pattern: $UPPERCASE_NAME (must start with letter or underscore)
        
        Args:
            template: Template string
        
        Returns:
            Set of variable names (without $)
        """
        variables = set(self.VARIABLE_PATTERN.findall(template))
        return variables
    
    async def _resolve_variables(
        self, 
        variables: Set[str], 
        context: Optional[Dict[str, Any]],
        strict: bool = True
    ) -> Dict[str, str]:
        """
        Resolve all variables to their values with strict validation.
        
        Resolution priority:
        1. Direct value in context (e.g., context['TASK'] or context['task'])
        2. Manually registered providers (backward compatibility)
        3. Config-defined providers (from variable_config.yaml)
        4. ERROR if strict=True and variable undefined
        
        Args:
            variables: Set of variable names
            context: Context dictionary
            strict: If True, raise ValueError for undefined variables
        
        Returns:
            Dictionary mapping variable names to resolved values
        
        Raises:
            ValueError: If strict=True and any variable is undefined
        """
        if context is None:
            context = {}
        
        values = {}
        undefined_vars = []
        
        for var in variables:
            # Priority 1: Direct value in context (check both uppercase and lowercase)
            if var in context:
                values[var] = str(context[var])
                continue
            
            # Also check lowercase version (e.g., $TASK matches context['task'])
            var_lower = var.lower()
            if var_lower in context:
                values[var] = str(context[var_lower])
                continue
            
            # Priority 2: Manual provider (backward compatibility)
            if var in self.manual_providers:
                provider = self.manual_providers[var]
                
                try:
                    if asyncio.iscoroutinefunction(provider):
                        result = await provider(context)
                    else:
                        result = provider(context)
                    
                    values[var] = str(result) if result is not None else ''
                
                except Exception as e:
                    logger.error(f"Error resolving ${var} from manual provider: {e}", exc_info=True)
                    values[var] = f"[ERROR: {var}]"
                
                continue
            
            # Priority 3: Config-defined provider
            if var in self.variable_map:
                provider = self.variable_map[var]
                
                try:
                    if asyncio.iscoroutinefunction(provider):
                        result = await provider(context)
                    else:
                        result = provider(context)
                    
                    values[var] = str(result) if result is not None else ''
                
                except Exception as e:
                    logger.error(f"Error resolving ${var} from config provider: {e}", exc_info=True)
                    values[var] = f"[ERROR: {var}]"
                
                continue
            
            # Variable not found
            if strict:
                undefined_vars.append(var)
            else:
                logger.warning(f"No provider for ${var} - using placeholder")
                values[var] = f"[MISSING: {var}]"
        
        # Strict validation: Raise error if any variable is undefined
        if strict and undefined_vars:
            available_vars = sorted(self.get_available_variables())
            available_str = ', '.join([f'${v}' for v in available_vars[:20]])
            if len(available_vars) > 20:
                available_str += f', ... and {len(available_vars) - 20} more'
            
            raise ValueError(
                f"Undefined variables in prompt template: {', '.join([f'${v}' for v in undefined_vars])}\n"
                f"Available variables: {available_str}\n"
                f"Add missing variables to context or define them in variable_config.yaml"
            )
        
        return values
    
    def _replace_variables(self, template: str, values: Dict[str, str]) -> str:
        """
        Replace all $VARIABLE placeholders with their values.
        
        Args:
            template: Template string
            values: Dictionary mapping variable names to values
        
        Returns:
            Template with variables replaced
        """
        result = template
        for var, value in values.items():
            result = result.replace(f'${var}', value)
        return result
    
    async def render(
        self, 
        template_path: str, 
        context: Optional[Dict[str, Any]] = None,
        strict: bool = True
    ) -> str:
        """
        Load template and render with variable substitution.
        
        This is the main entry point for prompt rendering.
        
        Args:
            template_path: Relative path to template (e.g. 'high_level/planning.txt')
            context: Context dictionary with data for variable resolution.
                    Should include: state, agent_name, memory_manager, etc.
            strict: If True, raise ValueError for undefined variables (recommended)
        
        Returns:
            Rendered prompt string
        
        Raises:
            ValueError: If strict=True and template contains undefined variables
        
        Example:
            prompt = await manager.render(
                'high_level/planning.txt',
                context={
                    'state': game_state,
                    'agent_name': 'BrainyBot',
                    'memory_manager': self.memory_manager,
                    'task_stack_manager': self.task_stack_manager,
                    'high_brain': self
                }
            )
        """
        # Load template (with caching)
        template = self._load_template(template_path)
        
        # Extract all variables
        variables = self._extract_variables(template)
        
        if not variables:
            # No variables to replace - return template as-is
            return template
        
        # Resolve all variables to values (with strict validation)
        values = await self._resolve_variables(variables, context, strict=strict)
        
        # Replace all variables
        result = self._replace_variables(template, values)
        
        logger.debug(f"Rendered template: {template_path} ({len(variables)} variables)")
        
        return result
    
    def render_sync(
        self, 
        template_path: str, 
        context: Optional[Dict[str, Any]] = None,
        strict: bool = True
    ) -> str:
        """
        Synchronous version of render() for non-async contexts.
        
        WARNING: This will fail if any required provider is async.
        Use render() (async) whenever possible.
        
        Args:
            template_path: Relative path to template
            context: Context dictionary
            strict: If True, raise ValueError for undefined variables
        
        Returns:
            Rendered prompt string
        
        Raises:
            ValueError: If strict=True and template contains undefined variables
        """
        # Load template
        template = self._load_template(template_path)
        
        # Extract variables
        variables = self._extract_variables(template)
        
        if not variables:
            return template
        
        # Resolve variables synchronously
        if context is None:
            context = {}
        
        values = {}
        undefined_vars = []
        
        for var in variables:
            # Priority 1: Direct value in context
            if var in context:
                values[var] = str(context[var])
                continue
            
            # Priority 2: Manual provider
            if var in self.manual_providers:
                provider = self.manual_providers[var]
                
                if asyncio.iscoroutinefunction(provider):
                    logger.error(
                        f"Cannot use async provider for ${var} in sync render. "
                        "Use render() (async) instead."
                    )
                    values[var] = f"[ASYNC_ERROR: {var}]"
                else:
                    try:
                        result = provider(context)
                        values[var] = str(result) if result is not None else ''
                    except Exception as e:
                        logger.error(f"Error resolving ${var}: {e}")
                        values[var] = f"[ERROR: {var}]"
                continue
            
            # Priority 3: Config provider
            if var in self.variable_map:
                provider = self.variable_map[var]
                
                if asyncio.iscoroutinefunction(provider):
                    logger.error(
                        f"Cannot use async provider for ${var} in sync render. "
                        "Use render() (async) instead."
                    )
                    values[var] = f"[ASYNC_ERROR: {var}]"
                else:
                    try:
                        result = provider(context)
                        values[var] = str(result) if result is not None else ''
                    except Exception as e:
                        logger.error(f"Error resolving ${var}: {e}")
                        values[var] = f"[ERROR: {var}]"
                continue
            
            # Variable not found
            if strict:
                undefined_vars.append(var)
            else:
                logger.warning(f"No provider for ${var}")
                values[var] = f"[MISSING: {var}]"
        
        # Strict validation
        if strict and undefined_vars:
            available_vars = sorted(self.get_available_variables())
            available_str = ', '.join([f'${v}' for v in available_vars[:20]])
            if len(available_vars) > 20:
                available_str += f', ... and {len(available_vars) - 20} more'
            
            raise ValueError(
                f"Undefined variables in prompt template: {', '.join([f'${v}' for v in undefined_vars])}\n"
                f"Available variables: {available_str}"
            )
        
        # Replace variables
        result = self._replace_variables(template, values)
        
        return result
