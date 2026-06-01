"""ChromaDB-based RAG knowledge base for test case generation."""

import json
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_KNOWLEDGE: List[str] = [
    json.dumps({
        "type": "business_rule",
        "rule": "登录后，token 应放入请求头 Authorization 字段，格式为 Bearer {token}",
        "applies_to": "所有需要认证的接口",
    }, ensure_ascii=False),
    json.dumps({
        "type": "business_rule",
        "rule": "创建资源（如订单、优惠券）后，返回的 ID 应被后续查询、更新、删除操作引用",
        "applies_to": "CRUD 业务链路",
    }, ensure_ascii=False),
    json.dumps({
        "type": "dependency_pattern",
        "pattern": "登录步骤的 token 被后续步骤引用时，Trans 格式：token=Step01.data.token",
        "applies_to": "所有包含登录的链路",
    }, ensure_ascii=False),
    json.dumps({
        "type": "boundary_rule",
        "rule": "分页参数 pageSize 通常范围 1-100，默认 20；pageNum 从 1 开始",
        "applies_to": "所有分页接口",
    }, ensure_ascii=False),
    json.dumps({
        "type": "defect_pattern",
        "pattern": "金额字段需验证精度（通常保留两位小数），空值/NULL 需特殊处理",
        "applies_to": "涉及金额的接口",
    }, ensure_ascii=False),
    json.dumps({
        "type": "defect_pattern",
        "pattern": "日期时间字段需验证格式（ISO8601），以及时区处理是否正确",
        "applies_to": "涉及日期时间的接口",
    }, ensure_ascii=False),
    json.dumps({
        "type": "test_strategy",
        "strategy": "正向用例验证正常业务流程；负向用例验证参数校验（必填缺失、类型错误、超长等）；边界用例验证极值行为；业务异常验证状态机（如重复操作、过期操作）",
        "applies_to": "所有接口",
    }, ensure_ascii=False),
    json.dumps({
        "type": "trans_format",
        "rule": "Trans 字段格式：key=StepID.response.field.path。多个键值对用逗号+空格分隔。路径使用点号分隔嵌套字段，数组用 [index] 访问",
        "applies_to": "所有业务链路用例",
    }, ensure_ascii=False),
]


class RAGKnowledgeBase:
    """ChromaDB-backed knowledge base for test case generation.

    Falls back to in-memory search if ChromaDB is unavailable.
    """

    def __init__(self, db_path: str = "./chroma_data"):
        self._db_path = db_path
        self._collection = None
        self._initialized = False
        self._fallback_docs = list(_DEFAULT_KNOWLEDGE)

    def initialize(self) -> None:
        """Initialize ChromaDB collection with default knowledge."""
        if self._initialized:
            return

        try:
            import chromadb
            os.makedirs(self._db_path, exist_ok=True)
            client = chromadb.PersistentClient(path=self._db_path)
            try:
                collection = client.get_collection("test_knowledge")
            except Exception:
                collection = client.create_collection("test_knowledge")
                ids = [f"kb_{i}" for i in range(len(_DEFAULT_KNOWLEDGE))]
                collection.add(
                    ids=ids,
                    documents=_DEFAULT_KNOWLEDGE,
                )
            self._collection = collection
            logger.info(
                "ChromaDB initialized at %s with %d documents",
                self._db_path,
                collection.count(),
            )
        except Exception as e:
            logger.warning(
                "ChromaDB unavailable (%s), using in-memory fallback with %d docs",
                e,
                len(self._fallback_docs),
            )
            self._collection = None

        self._initialized = True

    def query(self, text: str, n_results: int = 3) -> List[str]:
        """Search for relevant knowledge snippets."""
        if not self._initialized:
            self.initialize()

        if self._collection is not None:
            try:
                results = self._collection.query(
                    query_texts=[text], n_results=n_results
                )
                docs = results.get("documents", [[]])[0]
                if docs:
                    return docs
            except Exception as e:
                logger.warning("ChromaDB query failed: %s, falling back", e)

        return self._fallback_query(text, n_results)

    def _fallback_query(self, text: str, n_results: int) -> List[str]:
        """Simple keyword-based fallback search."""
        keywords = set(text.lower().split())
        scored = []
        for doc in self._fallback_docs:
            doc_lower = doc.lower()
            score = sum(1 for kw in keywords if kw in doc_lower)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:n_results]]

    def add_knowledge(self, documents: List[str]) -> None:
        """Add custom knowledge documents."""
        if not self._initialized:
            self.initialize()

        self._fallback_docs.extend(documents)

        if self._collection is not None:
            try:
                existing_count = self._collection.count()
                ids = [f"kb_{existing_count + i}" for i in range(len(documents))]
                self._collection.add(ids=ids, documents=documents)
            except Exception as e:
                logger.warning("Failed to add to ChromaDB: %s", e)
