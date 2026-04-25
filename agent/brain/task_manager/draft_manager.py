"""
Draft Manager

Manages the agent's draft file (bots/{name}/draft.md).
Used for current-step technical thinking — the coding scratchpad that both
the decision LLM and the coding LLM can read.

Replaces the old task.md (coding scratchpad) with clearer semantics:
draft = current step's technical thoughts, not a task plan.
"""

import os
import logging

logger = logging.getLogger(__name__)


class DraftManager:
    """
    Manages the agent's draft.md file.

    The draft file records current-step technical thinking:
    - Approach for the current todolist item
    - Failed attempts and what to try next
    - API usage notes, coordinates, temporary observations

    Read by both Agent Loop (for context) and Execution Layer (for coding hints).

    File location: bots/{agent_name}/draft.md
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.draft_dir = os.path.join(str(project_root), 'bots', agent_name)
        self.draft_file = os.path.join(self.draft_dir, 'draft.md')
        logger.info(f"DraftManager initialized: {self.draft_file}")

    def read(self) -> str:
        try:
            with open(self.draft_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.debug(f"Read draft file ({len(content)} chars)")
            return content
        except FileNotFoundError:
            logger.debug("Draft file does not exist, returning empty string")
            return ''
        except Exception as e:
            logger.error(f"Error reading draft file: {e}")
            return ''

    def write(self, content: str):
        try:
            os.makedirs(self.draft_dir, exist_ok=True)
            with open(self.draft_file, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.debug(f"Wrote draft file ({len(content)} chars)")
        except Exception as e:
            logger.error(f"Error writing draft file: {e}")
            raise

    def clear(self):
        self.write('')
        logger.info("Draft file cleared")
