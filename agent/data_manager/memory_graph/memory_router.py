"""
图记忆路由器 - 高层大脑核心接口

这是一个在 GraphEngine 和 GraphRetriever 之上的简洁封装层。
用来替代旧的五层扁平化记忆架构，正式启用动态的图记忆网络（Graph Memory Network）。
"""

import logging
import json
import re
import os
from typing import Dict, Any, List

from .graph_engine import GraphEngine
from .graph_retriever import GraphRetriever
from prompts.prompt_logger import PromptLogger

logger = logging.getLogger(__name__)

class MemoryRouter:
    """
    大脑（Brain）用于与图基础记忆网络进行交互的主要接口类。
    由于旧有的代码使用的是 MemoryRouter 的名字，为平滑过渡并兼容，保持此名称。
    """
    def __init__(self, agent_name: str, enable_logging: bool = True):
        self.agent_name = agent_name
        self.engine = GraphEngine(agent_name)
        self.retriever = GraphRetriever(self.engine)
        self.prompt_logger = PromptLogger("bots", agent_name, enabled=enable_logging)
        
        # 预加载抽取提示词模板
        prompt_path = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "memory", "memory_graph_extraction.txt")
        self.extraction_prompt_template = ""
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.extraction_prompt_template = f.read()
        except Exception as e:
            logger.warning(f"未能加载记忆图谱抽取提示词模板: {e}")

        logger.info(f"MemoryRouter 初始化完成 '{agent_name}'。开启图网络记忆引擎。")

    def experience(self, event_description: str, context_hints: Dict[str, Any] = None) -> str:
        """
        [自动连线器 ContextLinker] 
        记录新的体验（Event）。引擎在底层会自动把它与周围的上下文节点（地点、任务、实体等）硬连接起来。
        
        引数:
            event_description: 发生了什么的文字描述
            context_hints: 包含诸如 {"place": {"name": "村庄", "pos": [x,y,z]}, "entities": ["僵尸", "Notch"]} 等结构化信息
        """
        # 1. 创立事件节点
        event_node = self.engine.add_node(
            node_type="event",
            content=event_description,
            metadata={"source": "experience_log"}
        )
        
        if not context_hints:
            return event_node.id
            
        # 2. 自动建立空间与实体关联 (隐式连线)
        # 2.1 建立地点关联
        place_info = context_hints.get("place")
        if place_info:
            place_name = place_info.get("name", "未知地点")
            # 查找或创建地点节点
            existing_places = self.engine.find_nodes_by_type("place")
            place_node = next((p for p in existing_places if place_name in p.content), None)
            if not place_node:
                place_node = self.engine.add_node("place", content=place_name, metadata=place_info)
            # 建立边: [事件] -HAPPENED_AT-> [地点]
            self.engine.add_edge(event_node.id, place_node.id, relation="HAPPENED_AT", weight=1.0)
                
        # 2.2 建立相关实体交互关联
        entities = context_hints.get("entities", [])
        for ent_name in entities:
            existing_ents = self.engine.find_nodes_by_type("entity")
            ent_node = next((e for e in existing_ents if ent_name in e.content), None)
            if not ent_node:
                ent_node = self.engine.add_node("entity", content=ent_name)
            # 建立边: [事件] -INVOLVES-> [实体]
            self.engine.add_edge(event_node.id, ent_node.id, relation="INVOLVES", weight=0.8)
            
        return event_node.id

    async def reflect(self, llm_wrapper, recent_events_count: int = 5) -> None:
        """
        [大模型显式图谱提取机制 GraphRAG]
        由思考管理器（ContemplationManager）或休息时定期触发。
        大模型查看最近的一批 event，总结出模式或者新事实，并将节点关系图谱抽取入库。
        """
        if not self.extraction_prompt_template:
            logger.error("缺少图谱提取提示词模板，跳过 reflect")
            return

        # 获取最近发生的事件节点
        all_events = self.engine.find_nodes_by_type("event")
        recent_events = sorted(all_events, key=lambda n: n.created_at, reverse=True)[:recent_events_count]
        
        if not recent_events:
            return

        events_text = "\n".join([f"- {ev.content}" for ev in recent_events])
        
        # 使用加载好的提示词模板构造请求
        extraction_prompt = self.extraction_prompt_template.replace("{events_text}", events_text)
        
        # 使用 PromptLogger 记录发送给大模型的 Prompt
        prompt_file = self.prompt_logger.log_prompt(
            prompt=extraction_prompt,
            brain_layer="memory_graph",
            prompt_type="graph_extraction"
        )
        
        try:
            # 调用底层 LLM 服务发送请求
            response = await llm_wrapper.send_request([{"role": "user", "content": extraction_prompt}])
            
            # 更新大模型返回结果到日志
            self.prompt_logger.update_response(prompt_file, response)
            
            # 使用简单的正则匹配 JSON，防止大模型话太多
            match = re.search(r'\{.*\}', response, re.DOTALL | re.MULTILINE)
            if match:
                data = json.loads(match.group(0))
                # 注入系统提取出的节点和边
                self._integrate_llm_extraction(data)
                logger.info("图谱抽取更新成功！")
        except Exception as e:
            logger.error(f"反思图谱抽取失败: {e}", exc_info=True)

    def _integrate_llm_extraction(self, graph_data: dict):
        """将大模型抓取的结构化 JSON 实体数据合并入在内存的图结构中"""
        content_to_id = {}
        # 合并节点
        for n in graph_data.get("nodes", []):
            content = n.get("content")
            n_type = n.get("type", "concept")
            
            # 简单去重：如果已有类似内容的节点，复用其 ID，并增加热度
            existing = [x for x in self.engine.find_nodes_by_type(n_type) if x.content == content]
            if existing:
                target_node = existing[0]
                content_to_id[content] = target_node.id
                target_node.access_count += 1
            else:
                new_node = self.engine.add_node(n_type, content)
                content_to_id[content] = new_node.id
                
        # 链接边关系
        for e in graph_data.get("edges", []):
            src_str = e.get("source")
            tgt_str = e.get("target")
            src_id = content_to_id.get(src_str)
            tgt_id = content_to_id.get(tgt_str)
            if src_id and tgt_id:
                self.engine.add_edge(src_id, tgt_id, relation=e.get("relation", "RELATED_TO"), weight=0.5)

    def retrieve_context(self, trigger_texts: List[str] = None, top_k: int = 8) -> str:
        """
        [大模型提示词注入 Context Injection]
        使用激活扩散算法，从触发词向外波及检索最有价值的记忆子图，并展平为可用于提示词（Prompt）注入的文本。
        """
        active_node_ids = []
        
        # 将传入的环境触发器文本关联到具体存在的 Node ID
        if trigger_texts:
            all_nodes = list(self.engine.nx_graph.nodes(data='data'))
            for _, node in all_nodes:
                if any(t in node.content for t in trigger_texts):
                    active_node_ids.append(node.id)
                        
        if not active_node_ids:
            # 降级：如果没有匹配上任何线索，取最新发生的事件作为扩散源
            events = self.engine.find_nodes_by_type("event")
            active_node_ids = [n.id for n in sorted(events, key=lambda n: n.created_at)[-2:]]

        if not active_node_ids:
            return "无相关记忆记录。"
            
        relevant_nodes = self.retriever.spread_activation(
            start_node_ids=active_node_ids,
            max_depth=2,
            top_k=top_k
        )
        
        # 将子图重组为大模型可理解的上下文文字注入
        lines = ["=== 相关联的记忆图谱切片 ==="]
        for node in relevant_nodes:
            edges = self.engine.nx_graph.out_edges(node.id, data=True)
            if edges:
                # 为了防止信息爆炸导致过拟合，每个节点只展示权重较高的重要连线部分
                for src, tgt, data in list(edges)[:3]: 
                    target_node = self.engine.get_node(tgt)
                    if target_node:
                        lines.append(f"[{node.type.upper()}] {node.content} --({data['relation']})--> [{target_node.type.upper()}] {target_node.content}")
            else:
                lines.append(f"[{node.type.upper()}] {node.content}")
                
        return "\n".join(lines)
