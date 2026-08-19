"""[短期/长期记忆 SQLite] 短期：对话轮次，默认保留 30 天；长期：画像类记忆，带简易去重。"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from appchef.common.logger import logger
from appchef.common.paths import MEMORY_DB

# --- 可调参数（商业化时可迁到配置中心）---
SHORT_TERM_RETENTION_DAYS = 30
LONG_TERM_SIMILARITY_THRESHOLD = 0.88  # 向量余弦近似阈值，用于防冗余


def _now() -> float:
    return time.time()


def _tokenize_cn(text: str) -> set[str]:
    """极简中文稀疏特征：提取连续汉字片段 + 二元字组，供 BM25/Jaccard 风格去重用。"""
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    if not chars:
        return set()
    bigrams = {"".join(chars[i : i + 2]) for i in range(len(chars) - 1)}
    words = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    return set(words) | bigrams | set(chars)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _cosine_vec(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


@dataclass
class LongTermMemoryRow:
    kind: str
    content: str


class MemoryStore:
    """线程安全的 SQLite 记忆层。"""

    def __init__(self, db_path: str | None = None) -> None:
        self._path = db_path or str(MEMORY_DB)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS short_term_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_st_thread_time
                ON short_term_turns(thread_id, created_at);

            CREATE TABLE IF NOT EXISTS long_term_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                sparse_tokens TEXT,
                embedding_json TEXT,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_lt_user_kind
                ON long_term_memories(user_id, kind);

            CREATE TABLE IF NOT EXISTS recipe_rejection_state (
                thread_id TEXT PRIMARY KEY,
                reject_count INTEGER NOT NULL DEFAULT 0,
                recent_recipes TEXT,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS festival_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                reminder_type TEXT NOT NULL,
                festival_name TEXT,
                season TEXT,
                weather_condition TEXT,
                message TEXT NOT NULL,
                dismissed INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_fr_user_dismissed
                ON festival_reminders(user_id, dismissed);

            -- 用户提醒设置表：存储每个用户对特定提醒的开关状态
            CREATE TABLE IF NOT EXISTS user_reminder_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                reminder_type TEXT NOT NULL,  -- festival/seasonal
                reminder_name TEXT NOT NULL,  -- 节日名称或季节名称
                enabled INTEGER NOT NULL DEFAULT 1,  -- 1:开启, 0:关闭
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_urs_user_type
                ON user_reminder_settings(user_id, reminder_type, reminder_name);

            -- 菜谱反馈记录表：记录用户对推荐菜谱的反馈
            CREATE TABLE IF NOT EXISTS recipe_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                recipe_name TEXT NOT NULL,
                feedback_type TEXT NOT NULL,  -- like/dislike/neutral
                feedback_reason TEXT,  -- 不喜欢的原因：口味不合/过敏/其他
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rf_thread_user
                ON recipe_feedback(thread_id, user_id);

            -- RAG过程日志表：记录检索、评分、重写等过程
            CREATE TABLE IF NOT EXISTS rag_process_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                query TEXT NOT NULL,
                document_id INTEGER,
                chunk_id INTEGER,
                step_type TEXT NOT NULL,  -- retrieval/scoring/rewriting
                details TEXT,  -- 过程详情，JSON格式
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_rpl_user_query
                ON rag_process_logs(user_id, query);

            -- 用户偏好设置表：存储用户个性化设置
            CREATE TABLE IF NOT EXISTS user_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                preference_key TEXT NOT NULL,  -- 如：default_recipe_count, auto_terminate
                preference_value TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_up_user_key
                ON user_preferences(user_id, preference_key);
            """
        )
        self._conn.commit()

    def prune_short_term(self) -> int:
        """删除超过保留期的短期记忆，返回删除行数。"""
        cutoff = _now() - SHORT_TERM_RETENTION_DAYS * 86400
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM short_term_turns WHERE created_at < ?", (cutoff,))
            n = cur.rowcount or 0
            self._conn.commit()
        if n:
            logger.info("[MemoryStore] 清理过期短期记忆 %s 条（>%s 天）", n, SHORT_TERM_RETENTION_DAYS)
        return n

    def append_short_term(self, thread_id: str, role: str, content: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO short_term_turns (thread_id, role, content, created_at) VALUES (?,?,?,?)",
                (thread_id, role, content, _now()),
            )
            self._conn.commit()

    def recent_short_term_text(self, thread_id: str, limit: int = 12) -> str:
        """拼成供模型参考的短期对话摘要（按时间正序）。"""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT role, content FROM short_term_turns
                WHERE thread_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (thread_id, limit),
            ).fetchall()
        if not rows:
            return ""
        lines = []
        for r in reversed(list(rows)):
            role = r["role"]
            content = (r["content"] or "").strip()
            if not content:
                continue
            tag = "用户" if role == "user" else "助手" if role == "assistant" else role
            lines.append(f"- {tag}: {content[:500]}")
        return "\n".join(lines)

    def list_long_term(self, user_id: str, kinds: Optional[Iterable[str]] = None) -> list[LongTermMemoryRow]:
        with self._lock:
            if kinds:
                kind_list = list(kinds)
                placeholders = ",".join("?" * len(kind_list))
                q = f"SELECT kind, content FROM long_term_memories WHERE user_id = ? AND kind IN ({placeholders}) ORDER BY id"
                rows = self._conn.execute(q, (user_id, *tuple(kind_list))).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT kind, content FROM long_term_memories WHERE user_id = ? ORDER BY id",
                    (user_id,),
                ).fetchall()
        return [LongTermMemoryRow(kind=r["kind"], content=r["content"]) for r in rows]

    def long_term_prompt_block(self, user_id: str) -> str:
        rows = self.list_long_term(user_id)
        if not rows:
            return ""
        parts = []
        for r in rows:
            parts.append(f"- [{r.kind}] {r.content}")
        return "【长期用户画像】\n" + "\n".join(parts)

    def add_long_term(
        self,
        user_id: str,
        kind: str,
        content: str,
        embedding: Optional[list[float]] = None,
    ) -> bool:
        """
        写入长期记忆；若与已有记忆（同 kind）在稀疏或向量上高度重合则跳过。
        返回 True 表示已写入。
        """
        content = (content or "").strip()
        if not content:
            return False
        tokens = _tokenize_cn(content)
        sparse_json = json.dumps(sorted(tokens), ensure_ascii=False)
        emb_json = json.dumps(embedding, ensure_ascii=False) if embedding else None

        with self._lock:
            existing = self._conn.execute(
                "SELECT content, sparse_tokens, embedding_json FROM long_term_memories WHERE user_id = ? AND kind = ?",
                (user_id, kind),
            ).fetchall()
            for ex in existing:
                ex_tokens = set(json.loads(ex["sparse_tokens"] or "[]"))
                if _jaccard(tokens, ex_tokens) >= 0.72:
                    logger.info("[MemoryStore] 跳过冗余长期记忆(Jaccard): %s", content[:80])
                    return False
                if embedding and ex["embedding_json"]:
                    try:
                        prev = json.loads(ex["embedding_json"])
                        if isinstance(prev, list) and _cosine_vec(embedding, prev) >= LONG_TERM_SIMILARITY_THRESHOLD:
                            logger.info("[MemoryStore] 跳过冗余长期记忆(向量): %s", content[:80])
                            return False
                    except (json.JSONDecodeError, TypeError):
                        pass

            self._conn.execute(
                """
                INSERT INTO long_term_memories (user_id, kind, content, sparse_tokens, embedding_json, created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (user_id, kind, content, sparse_json, emb_json, _now()),
            )
            self._conn.commit()
        logger.info("[MemoryStore] 写入长期记忆 kind=%s user=%s", kind, user_id)
        return True

    # --- 拒绝 / 反思状态 ---
    def get_rejection_state(self, thread_id: str) -> tuple[int, list[str]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT reject_count, recent_recipes FROM recipe_rejection_state WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if not row:
            return 0, []
        try:
            recipes = json.loads(row["recent_recipes"] or "[]")
        except json.JSONDecodeError:
            recipes = []
        return int(row["reject_count"] or 0), recipes if isinstance(recipes, list) else []

    def record_recipe_rejection(self, thread_id: str, recipe_name: str) -> tuple[int, list[str]]:
        count, recent = self.get_rejection_state(thread_id)
        count += 1
        recent = (recent + [recipe_name])[-5:]
        payload = json.dumps(recent, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO recipe_rejection_state (thread_id, reject_count, recent_recipes, updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    reject_count = excluded.reject_count,
                    recent_recipes = excluded.recent_recipes,
                    updated_at = excluded.updated_at
                """,
                (thread_id, count, payload, _now()),
            )
            self._conn.commit()
        return count, recent

    def reset_rejection_state(self, thread_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM recipe_rejection_state WHERE thread_id = ?", (thread_id,))
            self._conn.commit()

    # --- 用户提醒设置 ---
    def get_reminder_settings(self, user_id: str) -> dict:
        """获取用户的提醒设置"""
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT reminder_type, reminder_name, enabled 
                FROM user_reminder_settings 
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchall()
        settings = {}
        for row in rows:
            key = f"{row['reminder_type']}_{row['reminder_name']}"
            settings[key] = bool(row['enabled'])
        return settings

    def update_reminder_setting(self, user_id: str, reminder_type: str, reminder_name: str, enabled: bool) -> None:
        """更新用户的提醒设置"""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO user_reminder_settings (user_id, reminder_type, reminder_name, enabled, created_at, updated_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(user_id, reminder_type, reminder_name) DO UPDATE SET
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (user_id, reminder_type, reminder_name, int(enabled), _now(), _now()),
            )
            self._conn.commit()

    # --- 菜谱反馈记录 ---
    def record_recipe_feedback(self, thread_id: str, user_id: str, recipe_name: str, feedback_type: str, feedback_reason: str = None) -> None:
        """记录菜谱反馈"""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO recipe_feedback (thread_id, user_id, recipe_name, feedback_type, feedback_reason, created_at)
                VALUES (?,?,?,?,?,?)
                """,
                (thread_id, user_id, recipe_name, feedback_type, feedback_reason, _now()),
            )
            self._conn.commit()

    # --- RAG过程日志 ---
    def log_rag_process(self, user_id: str, query: str, document_id: int, chunk_id: int, step_type: str, details: dict) -> None:
        """记录RAG过程日志"""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO rag_process_logs (user_id, query, document_id, chunk_id, step_type, details, created_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (user_id, query, document_id, chunk_id, step_type, json.dumps(details), _now()),
            )
            self._conn.commit()

    # --- 用户偏好设置 ---
    def get_user_preference(self, user_id: str, preference_key: str) -> str | None:
        """获取用户偏好设置"""
        with self._lock:
            row = self._conn.execute(
                """
                SELECT preference_value FROM user_preferences 
                WHERE user_id = ? AND preference_key = ?
                """,
                (user_id, preference_key),
            ).fetchone()
        return row['preference_value'] if row else None

    def set_user_preference(self, user_id: str, preference_key: str, preference_value: str) -> None:
        """设置用户偏好设置"""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO user_preferences (user_id, preference_key, preference_value, created_at, updated_at)
                VALUES (?,?,?,?,?)
                ON CONFLICT(user_id, preference_key) DO UPDATE SET
                    preference_value = excluded.preference_value,
                    updated_at = excluded.updated_at
                """,
                (user_id, preference_key, preference_value, _now(), _now()),
            )
            self._conn.commit()


_STORE: Optional[MemoryStore] = None


def get_memory_store() -> MemoryStore:
    global _STORE
    if _STORE is None:
        _STORE = MemoryStore()
    return _STORE
