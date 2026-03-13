"""
Embedding Provider - 语义向量化与相似度检索

为记忆图谱提供语义匹配能力：
- 将节点内容向量化（通过 OpenAI 兼容的 embedding API）
- 缓存向量到内存和磁盘，避免重复调用
- 基于余弦相似度查找语义相近的节点
"""

import os
import json
import math
import logging
from typing import List, Dict, Tuple, Optional

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """计算两个向量的余弦相似度。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingProvider:
    """
    管理 embedding 的生成、缓存和语义检索。

    支持 OpenAI / Qwen / DeepSeek / Ollama 等兼容 OpenAI embedding 接口的服务。
    """

    def __init__(self, agent_name: str, embedding_config: Dict = None):
        """
        Args:
            agent_name: 用于定位缓存目录
            embedding_config: embedding 配置，格式示例：
                {"api": "qwen", "url": "https://...", "model": "text-embedding-v3"}
                或简写 "openai" / "qwen" / "ollama"
        """
        self.agent_name = agent_name
        self._cache: Dict[str, List[float]] = {}  # node_id -> vector
        self._text_cache: Dict[str, str] = {}  # node_id -> content (用于检测内容变化)

        self._cache_path = os.path.join("bots", agent_name, "memory_graph", "embeddings.json")
        self._client: Optional[AsyncOpenAI] = None
        self._model: str = ""
        self._enabled = False

        self._init_client(embedding_config or {})
        self._load_cache()

    def _init_client(self, config: Dict):
        """根据配置初始化 embedding 客户端。"""
        # 兼容简写格式：如 "embedding": "openai"
        if isinstance(config, str):
            config = {"api": config}

        api = config.get("api", "")
        if not api:
            logger.info("未配置 embedding，语义检索不可用，将使用精确匹配降级")
            return

        # 各服务的默认参数
        defaults = {
            "qwen": {
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": "text-embedding-v3",
                "key_env": "QWEN_API_KEY",
            },
            "openai": {
                "base_url": None,  # 使用 openai 默认值
                "model": "text-embedding-3-small",
                "key_env": "OPENAI_API_KEY",
            },
            "deepseek": {
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-embedding",
                "key_env": "DEEPSEEK_API_KEY",
            },
            "ollama": {
                "base_url": "http://localhost:11434/v1",
                "model": "nomic-embed-text",
                "key_env": None,
            },
        }

        d = defaults.get(api, {})
        base_url = config.get("url") or config.get("base_url") or d.get("base_url")
        self._model = config.get("model") or d.get("model", "")
        api_key = config.get("api_key")

        if not api_key:
            key_env = d.get("key_env")
            if key_env:
                api_key = os.getenv(key_env, "")

        # 从 keys.json 加载
        if not api_key:
            api_key = self._load_key_from_file(api)

        if not api_key and api != "ollama":
            logger.warning(f"Embedding API key 未找到 ({api})，语义检索不可用")
            return

        kwargs = {"api_key": api_key or "ollama"}
        if base_url:
            kwargs["base_url"] = base_url

        self._client = AsyncOpenAI(**kwargs)
        self._enabled = True
        logger.info(f"Embedding provider 初始化: api={api}, model={self._model}")

    @staticmethod
    def _load_key_from_file(api: str) -> str:
        """从 keys.json 加载 API key。"""
        keys_file = "keys.json"
        if not os.path.exists(keys_file):
            return ""
        try:
            with open(keys_file, "r") as f:
                keys = json.load(f)
            key_map = {
                "qwen": "QWEN_API_KEY",
                "openai": "OPENAI_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
            }
            return keys.get(key_map.get(api, ""), "")
        except Exception:
            return ""

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ==================== 向量生成 ====================

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        批量生成 embedding 向量。

        Args:
            texts: 要向量化的文本列表

        Returns:
            对应的向量列表
        """
        if not self._enabled or not texts:
            return []

        try:
            response = await self._client.embeddings.create(
                input=texts,
                model=self._model
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"Embedding API 调用失败: {e}")
            return []

    async def embed_text(self, text: str) -> Optional[List[float]]:
        """生成单条文本的 embedding。"""
        results = await self.embed_texts([text])
        return results[0] if results else None

    # ==================== 节点向量管理 ====================

    async def ensure_node_embeddings(self, nodes: list):
        """
        确保给定节点都有 embedding 缓存。
        只对缺失或内容变化的节点调用 API。

        Args:
            nodes: Node 对象列表
        """
        if not self._enabled:
            return

        to_embed = []
        for node in nodes:
            cached_text = self._text_cache.get(node.id)
            if cached_text != node.content:
                to_embed.append(node)

        if not to_embed:
            return

        # 批量请求（每批最多 10 条，DashScope/Qwen 上限为 10）
        batch_size = 10
        for i in range(0, len(to_embed), batch_size):
            batch = to_embed[i:i + batch_size]
            texts = [n.content for n in batch]
            vectors = await self.embed_texts(texts)
            if len(vectors) == len(batch):
                for node, vec in zip(batch, vectors):
                    self._cache[node.id] = vec
                    self._text_cache[node.id] = node.content

        self._save_cache()

    def get_node_embedding(self, node_id: str) -> Optional[List[float]]:
        """获取节点的缓存向量。"""
        return self._cache.get(node_id)

    # ==================== 语义检索 ====================

    async def find_similar_nodes(
        self,
        query_texts: List[str],
        candidate_nodes: list,
        top_k: int = 5,
        threshold: float = 0.3
    ) -> List[Tuple[object, float]]:
        """
        根据查询文本，在候选节点中找到语义最相似的节点。

        Args:
            query_texts: 查询文本列表（会取平均向量）
            candidate_nodes: 候选 Node 对象列表
            top_k: 返回数量
            threshold: 最低相似度阈值

        Returns:
            [(node, similarity_score), ...] 按相似度降序
        """
        if not self._enabled or not query_texts or not candidate_nodes:
            return []

        # 确保候选节点都有 embedding
        await self.ensure_node_embeddings(candidate_nodes)

        # 生成查询向量（多条文本取平均）
        query_vectors = await self.embed_texts(query_texts)
        if not query_vectors:
            return []

        dim = len(query_vectors[0])
        avg_query = [0.0] * dim
        for qv in query_vectors:
            for j in range(dim):
                avg_query[j] += qv[j]
        for j in range(dim):
            avg_query[j] /= len(query_vectors)

        # 计算相似度
        scored = []
        for node in candidate_nodes:
            vec = self._cache.get(node.id)
            if vec:
                sim = cosine_similarity(avg_query, vec)
                if sim >= threshold:
                    scored.append((node, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ==================== 缓存持久化 ====================

    def _save_cache(self):
        """将 embedding 缓存写入磁盘。"""
        try:
            os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
            data = {
                "vectors": {nid: vec for nid, vec in self._cache.items()},
                "texts": self._text_cache,
            }
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Embedding 缓存保存失败: {e}")

    def _load_cache(self):
        """从磁盘加载 embedding 缓存。"""
        if not os.path.exists(self._cache_path):
            return
        try:
            with open(self._cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._cache = data.get("vectors", {})
            self._text_cache = data.get("texts", {})
            logger.info(f"加载 embedding 缓存: {len(self._cache)} 条向量")
        except Exception as e:
            logger.warning(f"Embedding 缓存加载失败: {e}")

    def remove_node(self, node_id: str):
        """删除节点的缓存向量。"""
        self._cache.pop(node_id, None)
        self._text_cache.pop(node_id, None)
