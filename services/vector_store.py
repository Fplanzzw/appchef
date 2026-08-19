"""RAG 向量存储服务（SQLite + DashScope embedding + Jieba + BM25）"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
import time
from typing import Dict, List, Optional, Tuple

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    logging.warning("jieba 未安装，BM25 检索将不可用")

from appchef.common.logger import logger
from appchef.common.paths import MEMORY_DB
from appchef.memory.embedding_dashscope import dashscope_text_embedding

# 加载自定义词典
if JIEBA_AVAILABLE:
    try:
        import pathlib
        vocab_path = pathlib.Path(__file__).parent.parent / "resources" / "food_vocab.txt"
        jieba.load_userdict(str(vocab_path))
        logger.info(f"已加载 Jieba 自定义词典: {vocab_path}")
    except Exception as e:
        logger.warning(f"加载 Jieba 自定义词典失败: {e}")


class VectorStoreService:
    """向量存储服务，支持混合检索（向量 + BM25）"""

    def __init__(self, db_path: str | None = None):
        self._path = db_path or str(MEMORY_DB)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """初始化数据库表"""
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS rag_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                upload_time REAL NOT NULL,
                chunk_count INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rd_user ON rag_documents(user_id);

            CREATE TABLE IF NOT EXISTS rag_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                chunk_text TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                bm25_tokens TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (doc_id) REFERENCES rag_documents(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_rc_doc ON rag_chunks(doc_id);
            """
        )
        self._conn.commit()

    def add_document(
        self,
        user_id: str,
        filename: str,
        file_type: str,
        chunks: List[str],
    ) -> int:
        """添加文档及其分块。

        Args:
            user_id: 用户ID
            filename: 文件名
            file_type: 文件类型
            chunks: 文本块列表

        Returns:
            文档ID
        """
        with self._lock:
            # 插入文档记录
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO rag_documents (user_id, filename, file_type, upload_time, chunk_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, filename, file_type, time.time(), len(chunks)),
            )
            doc_id = cur.lastrowid

            # 插入分块
            for chunk in chunks:
                embedding = dashscope_text_embedding(chunk)
                if not embedding:
                    logger.warning(f"获取 embedding 失败，跳过 chunk: {chunk[:50]}...")
                    continue

                # BM25 tokens（jieba 分词）
                if JIEBA_AVAILABLE:
                    tokens = list(jieba.lcut(chunk))
                else:
                    # 降级：按字符分词
                    tokens = list(chunk)

                bm25_tokens_json = json.dumps(tokens, ensure_ascii=False)
                embedding_json = json.dumps(embedding, ensure_ascii=False)

                cur.execute(
                    """
                    INSERT INTO rag_chunks (doc_id, chunk_text, embedding_json, bm25_tokens, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (doc_id, chunk, embedding_json, bm25_tokens_json, time.time()),
                )

            self._conn.commit()
            logger.info(f"已添加文档 {filename}（ID={doc_id}），包含 {len(chunks)} 个分块")
            return doc_id

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot = sum(x * y for x, y in zip(vec1, vec2))
        norm1 = math.sqrt(sum(x * x for x in vec1))
        norm2 = math.sqrt(sum(y * y for y in vec2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    def _bm25_score(self, query_tokens: List[str], doc_tokens: List[str], k1: float = 1.5, b: float = 0.75) -> float:
        """计算 BM25 评分"""
        if not query_tokens or not doc_tokens:
            return 0.0

        # 词频统计
        tf = {}
        for token in doc_tokens:
            tf[token] = tf.get(token, 0) + 1

        # 计算评分
        score = 0.0
        for token in query_tokens:
            if token in tf:
                score += tf[token] / (tf[token] + k1 * (1 - b + b * (len(doc_tokens) / 1.0)))

        return score

    def search(
        self,
        user_id: str,
        query: str,
        top_k: int = 5,
        vector_weight: float = 0.7,
        bm25_weight: float = 0.3,
    ) -> List[Dict]:
        """混合检索（向量 + BM25）。

        Args:
            user_id: 用户ID
            query: 查询文本
            top_k: 返回Top-K结果
            vector_weight: 向量检索权重
            bm25_weight: BM25检索权重

        Returns:
            检索结果列表，每个元素包含 chunk_text, score, doc_info
        """
        # 开始记录RAG过程
        process_start_time = time.time()
        
        # 获取查询向量
        query_embedding = dashscope_text_embedding(query)
        if not query_embedding:
            logger.warning("获取查询 embedding 失败")
            return []

        # 查询分词
        if JIEBA_AVAILABLE:
            query_tokens = list(jieba.lcut(query))
        else:
            query_tokens = list(query)

        # 记录检索步骤
        retrieval_start_time = time.time()
        with self._lock:
            cur = self._conn.cursor()
            rows = cur.execute(
                """
                SELECT rc.id, rc.doc_id, rc.chunk_text, rc.embedding_json, rc.bm25_tokens,
                       rd.filename, rd.file_type
                FROM rag_chunks rc
                JOIN rag_documents rd ON rc.doc_id = rd.id
                WHERE rd.user_id = ?
                """,
                (user_id,),
            ).fetchall()

        if not rows:
            logger.info(f"用户 {user_id} 没有上传任何文档")
            return []

        # 记录检索完成
        retrieval_end_time = time.time()
        retrieval_time = retrieval_end_time - retrieval_start_time
        
        # 记录检索过程
        self._log_rag_process(user_id, query, None, None, "retrieval", {
            "retrieval_time": retrieval_time,
            "total_chunks": len(rows),
            "query_tokens": query_tokens
        })

        # 计算每个分块的评分
        results = []
        for row in rows:
            # 向量相似度
            chunk_embedding = json.loads(row["embedding_json"])
            vector_score = self._cosine_similarity(query_embedding, chunk_embedding)

            # BM25 评分
            doc_tokens = json.loads(row["bm25_tokens"])
            bm25_score = self._bm25_score(query_tokens, doc_tokens)

            # 混合评分
            final_score = vector_weight * vector_score + bm25_weight * bm25_score

            results.append({
                "chunk_id": row["id"],
                "doc_id": row["doc_id"],
                "chunk_text": row["chunk_text"],
                "vector_score": vector_score,
                "bm25_score": bm25_score,
                "final_score": final_score,
                "doc_info": {
                    "filename": row["filename"],
                    "file_type": row["file_type"],
                },
            })

        # 排序并返回 Top-K
        results.sort(key=lambda x: x["final_score"], reverse=True)
        
        # 记录评分过程
        scoring_time = time.time() - retrieval_end_time
        self._log_rag_process(user_id, query, None, None, "scoring", {
            "scoring_time": scoring_time,
            "top_k": top_k,
            "results_count": len(results)
        })
        
        # 记录重写过程（这里简化，实际可能需要更复杂的重写逻辑）
        rewriting_time = 0.0
        self._log_rag_process(user_id, query, None, None, "rewriting", {
            "rewriting_time": rewriting_time,
            "top_results": results[:top_k]
        })

        return results[:top_k]

    def _log_rag_process(self, user_id: str, query: str, document_id: int, chunk_id: int, step_type: str, details: dict):
        """记录RAG过程日志"""
        mem = get_memory_store()
        mem.log_rag_process(user_id, query, document_id, chunk_id, step_type, details)

    def get_status(self, user_id: str) -> Dict:
        """获取 RAG 状态信息。

        Args:
            user_id: 用户ID

        Returns:
            状态字典，包含文档数、分块数等
        """
        with self._lock:
            cur = self._conn.cursor()

            # 文档数量
            doc_count = cur.execute(
                "SELECT COUNT(*) as cnt FROM rag_documents WHERE user_id = ?",
                (user_id,),
            ).fetchone()["cnt"]

            # 分块数量
            chunk_count = cur.execute(
                """
                SELECT COUNT(*) as cnt
                FROM rag_chunks rc
                JOIN rag_documents rd ON rc.doc_id = rd.id
                WHERE rd.user_id = ?
                """,
                (user_id,),
            ).fetchone()["cnt"]

            # 最近上传的文档
            recent_docs = cur.execute(
                """
                SELECT filename, file_type, upload_time, chunk_count
                FROM rag_documents
                WHERE user_id = ?
                ORDER BY upload_time DESC
                LIMIT 5
                """,
                (user_id,),
            ).fetchall()

        return {
            "user_id": user_id,
            "document_count": doc_count,
            "chunk_count": chunk_count,
            "recent_documents": [
                {
                    "filename": r["filename"],
                    "file_type": r["file_type"],
                    "upload_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["upload_time"])),
                    "chunk_count": r["chunk_count"],
                }
                for r in recent_docs
            ],
        }

    def delete_document(self, doc_id: int) -> bool:
        """删除文档（级联删除分块）。

        Args:
            doc_id: 文档ID

        Returns:
            是否成功
        """
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM rag_documents WHERE id = ?", (doc_id,))
            self._conn.commit()
            deleted_count = cur.rowcount
            logger.info(f"已删除文档 ID={doc_id}，影响 {deleted_count} 行")
            return deleted_count > 0


# 全局实例
_vector_store: Optional[VectorStoreService] = None


def get_vector_store() -> VectorStoreService:
    """获取全局向量存储实例"""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStoreService()
    return _vector_store