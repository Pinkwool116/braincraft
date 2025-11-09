"""
Robust JSON Parser for LLM Responses

Utilities for extracting and parsing JSON from LLM responses that may contain:
- Markdown code blocks (```json ... ```)
- Plain JSON objects
- Nested braces in string fields (e.g., code snippets)
- Mixed text and JSON content
"""

import json
import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def extract_json_from_response(response: str, allow_incomplete: bool = False) -> Optional[str]:
    """
    Extract JSON string from LLM response text.
    
    This function handles various formats:
    1. JSON wrapped in markdown code blocks: ```json { ... } ```
    2. JSON wrapped in plain code blocks: ``` { ... } ```
    3. Raw JSON object in text: ... { ... } ...
    
    Uses intelligent brace matching to handle nested braces correctly,
    including those inside string fields (like JavaScript code).
    
    Args:
        response: LLM response text that may contain JSON
        allow_incomplete: If True, don't raise error for incomplete JSON (default: False)
    
    Returns:
        Extracted JSON string or None if not found
    
    Raises:
        ValueError: If JSON object not found or incomplete (unless allow_incomplete=True)
    
    Examples:
        >>> extract_json_from_response('```json\\n{"key": "value"}\\n```')
        '{"key": "value"}'
        
        >>> extract_json_from_response('Some text {"key": "value"} more text')
        '{"key": "value"}'
        
        >>> extract_json_from_response('{"code": "if (x) { return true; }"}')
        '{"code": "if (x) { return true; }"}'
    """
    if not response or not isinstance(response, str):
        raise ValueError("Response must be a non-empty string")
    
    response = response.strip()
    
    # Method 1: Try to extract from markdown code blocks
    # Pattern matches: ```json or ``` followed by content, handling multiline
    json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', response, re.DOTALL)
    if json_match:
        return json_match.group(1).strip()
    
    # Method 2: Use intelligent brace matching for raw JSON
    # Find the first opening brace
    start = response.find('{')
    if start == -1:
        raise ValueError("No JSON object found in response (no opening brace)")
    
    # Count braces to find the matching closing brace
    # Handle string escaping and quotes properly
    brace_count = 0
    in_string = False
    escape_next = False
    end = -1
    
    for i in range(start, len(response)):
        char = response[i]
        
        # Handle escape sequences
        if escape_next:
            escape_next = False
            continue
        
        if char == '\\':
            escape_next = True
            continue
        
        # Toggle string state on unescaped quotes
        if char == '"':
            in_string = not in_string
            continue
        
        # Only count braces outside of strings
        if not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                # Found matching closing brace
                if brace_count == 0:
                    end = i + 1
                    break
    
    if end > start:
        return response[start:end].strip()
    
    if allow_incomplete:
        logger.warning("Incomplete JSON object found (unmatched braces)")
        return None
    
    raise ValueError("No complete JSON object found in response (unmatched braces)")


def parse_json_response(
    response: str,
    required_fields: Optional[list] = None,
    default_values: Optional[Dict[str, Any]] = None,
    strict: bool = True
) -> Dict[str, Any]:
    """
    Parse JSON from LLM response with validation and defaults.
    
    This is the main function to use for parsing LLM JSON responses.
    It combines extraction and parsing with validation.
    
    Args:
        response: LLM response text containing JSON
        required_fields: List of field names that must be present (raises ValueError if missing)
        default_values: Dict of default values for optional fields
        strict: If True, raise ValueError on parse errors. If False, return default_values or {}
    
    Returns:
        Parsed JSON dict
    
    Raises:
        ValueError: If JSON parsing fails or required fields missing (only if strict=True)
    
    Examples:
        >>> parse_json_response('{"name": "test"}', required_fields=['name'])
        {'name': 'test'}
        
        >>> parse_json_response('{"x": 1}', default_values={'y': 2})
        {'x': 1, 'y': 2}
        
        >>> parse_json_response('invalid', strict=False)
        {}
    """
    try:
        # Extract JSON string from response
        json_str = extract_json_from_response(response, allow_incomplete=False)
        
        if json_str is None:
            raise ValueError("Failed to extract JSON from response")
        
        # Try to parse JSON string with strict mode first
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            # If strict parsing fails due to control characters, try with strict=False
            # This handles cases where LLM returns literal \n instead of escaped \\n
            if "control character" in str(e).lower():
                logger.debug("Strict JSON parsing failed, trying with strict=False")
                parsed = json.loads(json_str, strict=False)
            else:
                raise
        
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected JSON object (dict), got {type(parsed).__name__}")
        
        # Validate required fields
        if required_fields:
            missing_fields = [field for field in required_fields if field not in parsed]
            if missing_fields:
                raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
        
        # Apply default values for optional fields
        if default_values:
            for key, value in default_values.items():
                parsed.setdefault(key, value)
        
        return parsed
    
    except (ValueError, json.JSONDecodeError) as e:
        if strict:
            # Re-raise with more context
            error_msg = f"Failed to parse JSON from LLM response: {e}"
            logger.error(error_msg)
            logger.debug(f"Response (first 500 chars): {response[:500]}")
            raise ValueError(error_msg) from e
        else:
            # Return defaults without raising
            logger.warning(f"JSON parse failed (non-strict mode): {e}")
            logger.debug(f"Response (first 500 chars): {response[:500]}")
            return default_values.copy() if default_values else {}


def parse_json_with_fallback(
    response: str,
    fallback_response: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Parse JSON from LLM response with fallback on failure.
    
    Convenience function that never raises exceptions.
    Useful for chat handlers where you want a default response on parse failure.
    
    Args:
        response: LLM response text containing JSON
        fallback_response: Dict to return if parsing fails (default: empty dict)
    
    Returns:
        Parsed JSON dict or fallback_response
    
    Examples:
        >>> parse_json_with_fallback('{"ok": true}')
        {'ok': True}
        
        >>> parse_json_with_fallback('invalid', {'error': True})
        {'error': True}
    """
    if fallback_response is None:
        fallback_response = {}
    
    try:
        return parse_json_response(response, strict=True)
    except (ValueError, json.JSONDecodeError):
        logger.debug("Using fallback response due to JSON parse failure")
        return fallback_response.copy()


def validate_json_fields(
    data: Dict[str, Any],
    field_validators: Dict[str, callable]
) -> bool:
    """
    Validate JSON fields using custom validator functions.
    
    Args:
        data: Parsed JSON dict
        field_validators: Dict mapping field names to validator functions
                         Each validator should return True if valid, False otherwise
    
    Returns:
        True if all validations pass, False otherwise
    
    Examples:
        >>> data = {'decision': 'continue', 'count': 5}
        >>> validators = {
        ...     'decision': lambda x: x in ['continue', 'stop'],
        ...     'count': lambda x: isinstance(x, int) and x > 0
        ... }
        >>> validate_json_fields(data, validators)
        True
    """
    for field, validator in field_validators.items():
        if field not in data:
            logger.warning(f"Field '{field}' not found in JSON")
            return False
        
        try:
            if not validator(data[field]):
                logger.warning(f"Validation failed for field '{field}': {data[field]}")
                return False
        except Exception as e:
            logger.error(f"Validator error for field '{field}': {e}")
            return False
    
    return True


# Convenience functions for common LLM response patterns

def parse_code_generation_response(response: str) -> Dict[str, Any]:
    """
    Parse LLM code generation response with reflection fields.
    
    Expected format (used by mid-level coding brain):
    {
        "analysis": "Analysis of the situation and approach",
        "decision": "continue|request_modification",
        "modification_request": "Request for high-level help (if decision=request_modification)",
        "code": "JavaScript code to execute"
    }
    
    Args:
        response: LLM response text from code generation prompt
    
    Returns:
        Parsed dict with code generation fields
    
    Raises:
        ValueError: If 'decision' field is missing
    """
    return parse_json_response(
        response,
        required_fields=['decision'],
        default_values={
            'analysis': '',
            'modification_request': '',
            'code': ''
        }
    )

def parse_chat_response(response: str) -> Dict[str, Any]:
    """
    Parse LLM chat response with standard fields.
    
    Expected format:
    {
        "message": "...",
        "task": "..." or null,
        "update_player_description": "..." or null
    }
    
    Args:
        response: LLM response text
    
    Returns:
        Parsed dict with chat fields
    """
    return parse_json_response(
        response,
        required_fields=['message'],
        default_values={
            'task': None,
            'update_player_description': None
        }
    )
