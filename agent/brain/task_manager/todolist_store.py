"""
TodoList Store

Structured Markdown-based todolist manager.
Single source of truth: bots/{name}/todolist.md

Each line format: {indent}- [{status}] {id} {text}
- Nesting: determined by ID numbering (primary) + indentation (secondary)
- When they conflict, ID numbering wins.
"""

import os
import re
import logging
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

# Line pattern: leading spaces, "- [status_char] id text"
LINE_RE = re.compile(r'^(\s*)- \[(.)\] (\S+) (.+)$')


class TodoItem:
    """A single todolist node in the tree."""
    __slots__ = ('id', 'text', 'status', 'children', 'parent')

    def __init__(self, id: str, text: str, status: str = 'pending', parent: Optional['TodoItem'] = None):
        self.id = id
        self.text = text
        self.status = status  # 'pending' | 'in_progress' | 'done' | 'blocked'
        self.children: List[TodoItem] = []
        self.parent: Optional[TodoItem] = parent

    def is_ancestor_of(self, other: 'TodoItem') -> bool:
        """Check if self is an ancestor of other via ID numbering."""
        return other.id.startswith(self.id + '.') and other.id != self.id

    @property
    def depth(self) -> int:
        return self.id.count('.')


class TodoListStore:
    """
    Structured todolist backed by a single Markdown file.

    Dual-guarantee nesting:
    1. ID numbering (primary): t1.2 is always child of t1
    2. Indentation (secondary): 2 spaces per level, for human readability
    When they conflict, ID wins — the renderer normalizes indentation.
    """

    STATUS_CHARS = {
        'pending': ' ',
        'in_progress': '>',
        'done': 'x',
        'blocked': '!',
    }
    CHAR_STATUS = {v: k for k, v in STATUS_CHARS.items()}

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        from pathlib import Path
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.store_dir = os.path.join(str(project_root), 'bots', agent_name)
        self.md_path = os.path.join(self.store_dir, 'todolist.md')
        self._roots: List[TodoItem] = []
        self._id_index: Dict[str, TodoItem] = {}
        self._next_ids: Dict[str, int] = {}  # parent_id -> next child number
        self._load()
        logger.info(f"TodoListStore initialized: {self.md_path} ({len(self._id_index)} items)")

    # ── File I/O ──────────────────────────────────────────────

    def _load(self):
        """Parse todolist.md → tree. Rebuilds ID index and next-id counters."""
        self._roots.clear()
        self._id_index.clear()
        self._next_ids.clear()

        try:
            with open(self.md_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except FileNotFoundError:
            logger.debug("todolist.md not found, starting empty")
            return

        # Pass 1: parse all lines into flat items
        flat_items: List[dict] = []
        for line in lines:
            line = line.rstrip('\n\r')
            if not line.strip():
                continue
            m = LINE_RE.match(line)
            if not m:
                logger.warning(f"Skipping unrecognized todolist line: {line[:80]}")
                continue
            indent = m.group(1)
            status_char = m.group(2)
            item_id = m.group(3)
            text = m.group(4)
            status = self.CHAR_STATUS.get(status_char, 'pending')
            indent_level = len(indent) // 2 if indent else 0
            flat_items.append({
                'id': item_id,
                'text': text,
                'status': status,
                'indent_level': indent_level,
            })

        if not flat_items:
            return

        # Pass 2: build tree using ID numbering as ground truth
        for fi in flat_items:
            item = TodoItem(id=fi['id'], text=fi['text'], status=fi['status'])
            self._id_index[item.id] = item

            # Determine parent from ID numbering
            parent = self._find_parent_by_id(item.id)
            if parent:
                item.parent = parent
                parent.children.append(item)
            else:
                self._roots.append(item)

        # Rebuild next-id counters from existing IDs
        self._rebuild_id_counters()

        logger.debug(f"Loaded {len(self._id_index)} items from todolist.md")

    def _find_parent_by_id(self, item_id: str) -> Optional[TodoItem]:
        """Find parent by stripping the last segment of the ID."""
        last_dot = item_id.rfind('.')
        if last_dot == -1:
            return None  # Top-level item
        parent_id = item_id[:last_dot]
        return self._id_index.get(parent_id)

    def _rebuild_id_counters(self):
        """Scan all IDs and compute the next available number per parent prefix."""
        self._next_ids.clear()
        for item_id in self._id_index:
            last_dot = item_id.rfind('.')
            if last_dot == -1:
                # Top-level: e.g., "t3" → prefix "", suffix 3
                prefix = ''
                num_str = item_id[1:]  # after 't'
            else:
                prefix = item_id[:last_dot]  # e.g., "t1.2"
                num_str = item_id[last_dot + 2:]  # after '.t'
            try:
                num = int(num_str)
            except ValueError:
                continue
            current = self._next_ids.get(prefix, 0)
            if num >= current:
                self._next_ids[prefix] = num + 1

    def _save(self):
        """Render tree → Markdown and write to file."""
        os.makedirs(self.store_dir, exist_ok=True)
        lines = self._render_lines(self._roots, 0)
        content = '\n'.join(lines) + '\n'
        with open(self.md_path, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.debug(f"Saved {len(self._id_index)} items to todolist.md")

    # ── Rendering ─────────────────────────────────────────────

    def _render_lines(self, items: List[TodoItem], depth: int) -> List[str]:
        """Render a list of items at a given depth as Markdown lines."""
        lines = []
        indent = '  ' * depth
        for item in items:
            status_char = self.STATUS_CHARS.get(item.status, ' ')
            lines.append(f"{indent}- [{status_char}] {item.id} {item.text}")
            lines.extend(self._render_lines(item.children, depth + 1))
        return lines

    def get_markdown(self) -> str:
        """Return the full todolist as Markdown (for prompt injection)."""
        if not self._roots:
            return ''
        lines = self._render_lines(self._roots, 0)
        return '\n'.join(lines)

    # ── ID Allocation ─────────────────────────────────────────

    def _allocate_id(self, parent_id: Optional[str] = None) -> str:
        """Allocate the next available ID under the given parent."""
        prefix = parent_id if parent_id else ''
        next_num = self._next_ids.get(prefix, 1)
        self._next_ids[prefix] = next_num + 1
        if prefix:
            return f"{prefix}.t{next_num}"
        return f"t{next_num}"

    # ── Lookup ────────────────────────────────────────────────

    def _get_item(self, item_id: str) -> TodoItem:
        """Get item by ID, raising KeyError if not found."""
        item = self._id_index.get(item_id)
        if item is None:
            raise KeyError(f"Item not found: {item_id}")
        return item

    def _get_sibling_list(self, item: TodoItem) -> List[TodoItem]:
        """Get the list that contains this item (parent's children or roots)."""
        if item.parent:
            return item.parent.children
        return self._roots

    # ── Operations ────────────────────────────────────────────

    def add(self, text: str, parent_id: Optional[str] = None,
            position: str = 'end') -> str:
        """
        Add a new item. Returns the new ID.

        Args:
            text: Item description text
            parent_id: Parent ID (None = top-level)
            position: 'start' | 'end' | <int index>
        """
        parent = self._get_item(parent_id) if parent_id else None
        new_id = self._allocate_id(parent_id)
        item = TodoItem(id=new_id, text=text, status='pending', parent=parent)
        self._id_index[new_id] = item

        siblings = parent.children if parent else self._roots
        if position == 'start':
            siblings.insert(0, item)
        elif isinstance(position, int):
            siblings.insert(position, item)
        else:  # 'end'
            siblings.append(item)

        self._save()
        logger.info(f"Added item {new_id}: {text[:60]}")
        return new_id

    def remove(self, item_id: str):
        """Remove an item and all its descendants."""
        item = self._get_item(item_id)
        self._remove_recursive(item)
        self._save()
        logger.info(f"Removed item {item_id} and descendants")

    def _remove_recursive(self, item: TodoItem):
        for child in list(item.children):
            self._remove_recursive(child)
        siblings = self._get_sibling_list(item)
        if item in siblings:
            siblings.remove(item)
        del self._id_index[item.id]

    def update(self, item_id: str, text: str):
        """Update the text of an item."""
        item = self._get_item(item_id)
        item.text = text
        self._save()
        logger.info(f"Updated item {item_id}: {text[:60]}")

    def set_status(self, item_id: str, status: str):
        """
        Set the status of an item. Enforces unique in_progress:
        setting one item to in_progress demotes all others to pending.

        Returns:
            str: 'same_focus' if setting the same in_progress item again,
                 'new_focus' if focus moved to a different item,
                 'normal' otherwise
        """
        if status not in self.STATUS_CHARS:
            raise ValueError(f"Invalid status: {status}")

        item = self._get_item(item_id)
        old_status = item.status

        if status == 'in_progress':
            if old_status == 'in_progress':
                # Same item re-set to in_progress — no clearing needed
                self._save()
                return 'same_focus'
            # Demote all other in_progress items
            for other_id, other in self._id_index.items():
                if other.status == 'in_progress' and other_id != item_id:
                    other.status = 'pending'

        item.status = status
        self._save()
        logger.info(f"Set status {item_id}: {old_status} → {status}")

        if status == 'in_progress':
            return 'new_focus'
        return 'normal'

    def move(self, item_id: str, new_parent_id: str,
             position: str = 'end'):
        """
        Move an item to a new parent.

        Args:
            item_id: Item to move
            new_parent_id: Target parent ID
            position: 'start' | 'end' | <int index>
        """
        item = self._get_item(item_id)
        new_parent = self._get_item(new_parent_id)

        # Prevent moving to self or descendant
        if item is new_parent or new_parent.id.startswith(item.id + '.'):
            raise ValueError(f"Cannot move {item_id} under its own descendant {new_parent_id}")

        # Remove from old parent
        old_siblings = self._get_sibling_list(item)
        if item in old_siblings:
            old_siblings.remove(item)

        # Add to new parent
        new_siblings = new_parent.children
        if position == 'start':
            new_siblings.insert(0, item)
        elif isinstance(position, int):
            new_siblings.insert(position, item)
        else:
            new_siblings.append(item)

        item.parent = new_parent
        self._save()
        logger.info(f"Moved {item_id} under {new_parent_id}")

    def overwrite(self, markdown_content: str):
        """
        Replace the entire todolist with new Markdown content.
        Parses via dual-guarantee (ID numbering as ground truth),
        writes back normalized Markdown.
        """
        # Write the content to file first, then re-parse
        os.makedirs(self.store_dir, exist_ok=True)
        with open(self.md_path, 'w', encoding='utf-8') as f:
            f.write(markdown_content if markdown_content.endswith('\n') else markdown_content + '\n')
        # Re-parse — this normalizes indentation
        self._load()
        self._save()  # Write back normalized version
        logger.info(f"Overwritten todolist with {len(self._id_index)} items")

    def is_all_done(self) -> bool:
        """Check if all top-level items are done."""
        if not self._roots:
            return False
        return all(item.status == 'done' for item in self._roots)

    def get_in_progress_text(self) -> Optional[str]:
        """Return the text of the deepest in_progress leaf item, or None."""
        best = None
        best_depth = -1
        for item in self._id_index.values():
            if item.status == 'in_progress' and item.depth >= best_depth:
                best = item
                best_depth = item.depth
        return best.text if best else None
