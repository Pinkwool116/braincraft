"""
LLM Model Wrappers

Provides unified interface to different LLM APIs:
- OpenAI (GPT-4, GPT-4o, GPT-3.5)
- Anthropic (Claude)
- DeepSeek
- Qwen - Default
- Local models (Ollama)
"""

import logging
import json
from typing import List, Dict, Any, Optional
import os
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

class LLMModel:
    """
    Base class for LLM models
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize LLM model
        
        Args:
            config: Model configuration dictionary
        """
        self.model_name = config.get('model_name')
        self.api = config.get('api')
        self.params = config.get('params', {})
        self.base_url = config.get('base_url', None)
        
        logger.info(f"Initialized {self.api} model: {self.model_name}")
    
    async def send_request(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None
    ) -> str:
        """
        Send request to LLM
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt to prepend
        
        Returns:
            Generated text response
        """
        raise NotImplementedError("Subclass must implement send_request")


class OpenAIModel(LLMModel):
    """
    OpenAI API wrapper (GPT-4, GPT-4o, GPT-3.5-turbo)
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        api_key = config.get('api_key', os.getenv('OPENAI_API_KEY'))
        
        if not api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable or provide in config.")
        
        self.client = AsyncOpenAI(api_key=api_key)
        logger.info(f"OpenAI client initialized: {self.model_name}")
    
    async def send_request(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None
    ) -> str:
        """Send request to OpenAI API"""
        
        # Prepare messages
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=full_messages,
                temperature=self.params.get('temperature', 0.7),
                max_tokens=self.params.get('max_tokens', 2000),
                top_p=self.params.get('top_p', 1.0)
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise


class AnthropicModel(LLMModel):
    """
    Anthropic Claude API wrapper
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        api_key = config.get('api_key', os.getenv('ANTHROPIC_API_KEY'))
        
        if not api_key:
            raise ValueError("Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable or provide in config.")
        
        self.client = AsyncAnthropic(api_key=api_key)
        logger.info(f"Anthropic client initialized: {self.model_name}")
    
    async def send_request(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None
    ) -> str:
        """Send request to Anthropic API"""
        
        try:
            # Claude requires system parameter separately
            response = await self.client.messages.create(
                model=self.model_name,
                system=system_prompt if system_prompt else "",
                messages=messages if messages else [{"role": "user", "content": system_prompt or "Hello"}],
                temperature=self.params.get('temperature', 0.7),
                max_tokens=self.params.get('max_tokens', 2000)
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise


class DeepSeekModel(LLMModel):
    """
    DeepSeek API wrapper (OpenAI-compatible)
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        api_key = config.get('api_key', os.getenv('DEEPSEEK_API_KEY'))
        base_url = config.get('base_url', 'https://api.deepseek.com/v1')
        
        if not api_key:
            raise ValueError("DeepSeek API key not found. Set DEEPSEEK_API_KEY environment variable or provide in config.")
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        logger.info(f"DeepSeek client initialized: {self.model_name}")
    
    async def send_request(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None
    ) -> str:
        """Send request to DeepSeek API"""
        
        # Prepare messages
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=full_messages,
                temperature=self.params.get('temperature', 0.7),
                max_tokens=self.params.get('max_tokens', 2000)
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            raise


class OllamaModel(LLMModel):
    """
    Ollama local model wrapper (OpenAI-compatible endpoint)
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        base_url = config.get('base_url', 'http://localhost:11434/v1')
        
        # Ollama doesn't require API key
        self.client = AsyncOpenAI(
            api_key="ollama",  # Dummy key
            base_url=base_url
        )
        logger.info(f"Ollama client initialized: {self.model_name} at {base_url}")
    
    async def send_request(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None
    ) -> str:
        """Send request to Ollama API"""
        
        # Prepare messages
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=full_messages,
                temperature=self.params.get('temperature', 0.7),
                max_tokens=self.params.get('max_tokens', 2000)
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise


class QwenModel(LLMModel):
    """
    Qwen API wrapper
    
    Supports: qwen-max, qwen-plus, qwen-turbo
    Compatible with OpenAI API format via DashScope
    """
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        api_key = config.get('api_key', os.getenv('QWEN_API_KEY') or os.getenv('DASHSCOPE_API_KEY'))
        base_url = config.get('base_url', 'https://dashscope.aliyuncs.com/compatible-mode/v1')
        
        if not api_key:
            raise ValueError("Qwen API key not found. Set QWEN_API_KEY or DASHSCOPE_API_KEY environment variable or provide in config.")
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        logger.info(f"Qwen client initialized: {self.model_name}")
    
    async def send_request(
        self, 
        messages: List[Dict[str, str]], 
        system_prompt: str = None
    ) -> str:
        """Send request to Qwen API (OpenAI-compatible format)"""
        
        # Prepare messages
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=full_messages,
                temperature=self.params.get('temperature', 0.7),
                max_tokens=self.params.get('max_tokens', 2000),
                top_p=self.params.get('top_p', 1.0)
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Qwen API error: {e}")
            raise


def create_llm_model(config: Dict[str, Any]) -> LLMModel:
    """
    Factory function to create appropriate LLM model
    
    Args:
        config: Model configuration dict with 'api' field
    
    Returns:
        LLMModel instance
    """
    api = config.get('api', 'qwen')  # Default to Qwen
    
    model_map = {
        'openai': OpenAIModel,
        'anthropic': AnthropicModel,
        'claude': AnthropicModel,  # Alias
        'deepseek': DeepSeekModel,
        'ollama': OllamaModel,
        'qwen': QwenModel,
    }
    
    model_class = model_map.get(api)
    if not model_class:
        raise ValueError(f"Unknown API: {api}. Supported: {list(model_map.keys())}")
    
    return model_class(config)
