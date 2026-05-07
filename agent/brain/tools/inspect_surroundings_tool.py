"""
Inspect Surroundings Tool

On-demand detailed observation for nearby blocks and entities.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class InspectSurroundingsTool:
    """Tool: inspect_surroundings"""

    name: str = "inspect_surroundings"
    description: str = (
        "细致观察周围方块/实体。参数: radius=1..20; include='blocks'|'entities'|'both' "
        "(默认 both); targets=[方块或实体名称]，为空时观察默认重要目标; "
        "scan_mode='important'|'targets_only'|'all' (默认 important); "
        "focus=观察重点; limit=返回样例上限(默认80, 最大300)。"
        "radius<=3 时返回完整匹配信息，适合查脚边、头顶、建筑/挖掘的精确坐标。"
        "radius>3 时必须提供 focus，工具会围绕重点摘要，适合找资源、敌人、洞口、路线或风险。"
        "scan_mode='all' 数据量很大，半径不要太大；radius>3 且 all 时尤其要写清 focus。"
        "常用方块名示例: oak_log, birch_log, spruce_log, stone, coal_ore, iron_ore, "
        "copper_ore, gold_ore, diamond_ore, water, lava, chest, crafting_table, furnace, "
        "bed, wheat, torch, door, lever, button。"
        "常用实体名示例: player, zombie, skeleton, creeper, spider, enderman, cow, sheep, "
        "pig, chicken, villager, item, arrow。优先使用精确 Minecraft registry 名称。"
    )

    def __init__(self, ipc_server, perception_manager=None, timeout_seconds: float = 15.0):
        self.ipc_server = ipc_server
        self.perception_manager = perception_manager
        self.timeout_seconds = timeout_seconds
        self._pending: Dict[str, asyncio.Future] = {}

    async def execute(self, args: dict) -> dict:
        try:
            request = self._normalize_args(args or {})
        except ValueError as e:
            return {"success": False, "error": str(e)}

        warnings = request.pop("_warnings", [])

        request_id = str(uuid.uuid4())
        request["request_id"] = request_id

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future

        try:
            await self.ipc_server.send_command({
                "type": "inspect_surroundings_request",
                "data": request,
            })
            result = await asyncio.wait_for(future, timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            result = {"success": False, "error": "inspect_surroundings timed out waiting for JS result"}
            if warnings:
                result["_warnings"] = warnings
            return result
        except Exception as e:
            logger.error("inspect_surroundings request failed: %s", e, exc_info=True)
            return {"success": False, "error": str(e)}
        finally:
            self._pending.pop(request_id, None)

        if not result.get("success", False):
            if warnings:
                result["_warnings"] = warnings
            return result

        if request["radius"] > 3:
            result = await self._summarize_large_scan(request, result)

        if warnings:
            result["_warnings"] = warnings
        return result

    def handle_result(self, data: dict):
        request_id = data.get("request_id")
        if not request_id:
            return
        future = self._pending.get(request_id)
        if future and not future.done():
            future.set_result(data)

    def _normalize_args(self, args: dict) -> dict:
        warnings = []

        try:
            radius = int(args.get("radius", 3))
        except (TypeError, ValueError):
            raise ValueError("radius must be an integer from 1 to 20")
        if radius > 20:
            warnings.append(f"radius={radius} 超出最大值20，已截断为20。请下次使用 radius<=20")
            radius = 20
        radius = max(1, radius)

        include = str(args.get("include", "both")).lower()
        if include not in ("blocks", "entities", "both"):
            raise ValueError("include must be 'blocks', 'entities', or 'both'")

        scan_mode = str(args.get("scan_mode", "important")).lower()
        if scan_mode not in ("important", "targets_only", "all"):
            raise ValueError("scan_mode must be 'important', 'targets_only', or 'all'")

        raw_targets = args.get("targets", [])
        if raw_targets in (None, ""):
            targets = []
        elif isinstance(raw_targets, str):
            targets = [raw_targets]
        elif isinstance(raw_targets, list):
            targets = [str(t) for t in raw_targets if str(t).strip()]
        else:
            raise ValueError("targets must be a list of block/entity names or a string")
        targets = [t.strip() for t in targets]

        focus = str(args.get("focus", "")).strip()
        if radius > 3 and not focus:
            raise ValueError("radius > 3 requires a non-empty focus for summary")

        try:
            limit = int(args.get("limit", 80))
        except (TypeError, ValueError):
            limit = 80
        if limit > 300:
            warnings.append(f"limit={limit} 超出最大值300，已截断为300")
            limit = 300
        limit = max(1, limit)

        result = {
            "radius": radius,
            "include": include,
            "targets": targets,
            "scan_mode": scan_mode,
            "focus": focus,
            "limit": limit,
        }
        if warnings:
            result["_warnings"] = warnings
        return result

    async def _summarize_large_scan(self, request: dict, result: dict) -> dict:
        """Use perception LLM when available, then drop raw detail from large scans."""
        summary_input = {
            "request": request,
            "summary": result.get("summary", {}),
            "samples": result.get("samples", {}),
            "invalid_targets": result.get("invalid_targets", []),
            "suggestions": result.get("suggestions", {}),
        }

        llm_summary = None
        analyzer = getattr(self.perception_manager, "terrain_analyzer", None)
        llm = getattr(analyzer, "llm", None)
        if llm:
            prompt = (
                "你是 Minecraft 环境观察摘要器。根据结构化扫描结果，用中文围绕观察重点总结。\n"
                f"观察重点: {request.get('focus')}\n"
                "要求: 提炼关键方块/实体数量、最近坐标、方向分布、风险、下一步行动建议。"
                "不要编造扫描中没有的信息，保持简洁。\n\n"
                f"扫描数据:\n{json.dumps(summary_input, ensure_ascii=False, indent=2)}"
            )
            try:
                response = await llm.send_request([{"role": "user", "content": prompt}])
                if response:
                    llm_summary = response.strip()
            except Exception as e:
                logger.warning("inspect_surroundings LLM summary failed: %s", e)

        compact = {
            "success": True,
            "mode": "summary",
            "radius": request["radius"],
            "include": request["include"],
            "scan_mode": request["scan_mode"],
            "targets": request["targets"],
            "focus": request["focus"],
            "summary_text": llm_summary or result.get("summary_text") or "扫描完成，但摘要模型未返回文本；请查看结构化摘要。",
            "summary": result.get("summary", {}),
            "samples": result.get("samples", {}),
            "truncated": result.get("truncated", False),
        }
        if result.get("invalid_targets"):
            compact["invalid_targets"] = result["invalid_targets"]
            compact["suggestions"] = result.get("suggestions", {})
        return compact
