"""
memory/memory.py — Persistent local memory for MAX using SQLite.

Stores memories with:
- Full-text search
- Tag filtering
- User-scoped isolation
- Recency and relevance scoring
"""

import aiosqlite
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("MAX.memory")


@dataclass
class Memory:
    id: int
    content: str
    user_id: str
    tags: list[str]
    created_at: datetime
    accessed_at: datetime
    access_count: int


class MemoryStore:
    """
    SQLite-backed persistent memory store.
    Supports fuzzy search, tag filtering, and LRU-style access tracking.
    """

    def __init__(self, db_path: str = "./max_memory.db"):
        self.db_path = Path(db_path)
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info(f"Memory store opened at {self.db_path}")

    async def _create_tables(self):
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                tags        TEXT    NOT NULL DEFAULT '[]',
                created_at  TEXT    NOT NULL,
                accessed_at TEXT    NOT NULL,
                access_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id);
            CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(content, user_id UNINDEXED, tokenize='porter ascii');
        """)
        await self._db.commit()

    async def store(
        self,
        content: str,
        user_id: str = "default",
        tags: list[str] = None,
    ) -> int:
        """Store a new memory. Returns the memory ID."""
        now = datetime.utcnow().isoformat()
        tags_json = json.dumps(tags or [])

        async with self._db.execute(
            """
            INSERT INTO memories (user_id, content, tags, created_at, accessed_at, access_count)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (user_id, content, tags_json, now, now)
        ) as cursor:
            memory_id = cursor.lastrowid

        # Also insert into FTS table
        await self._db.execute(
            "INSERT INTO memories_fts (rowid, content, user_id) VALUES (?, ?, ?)",
            (memory_id, content, user_id)
        )
        await self._db.commit()

        logger.debug(f"Stored memory #{memory_id} for {user_id}: {content[:60]}...")
        return memory_id

    async def search(
        self,
        query: str,
        user_id: str = "default",
        limit: int = 5,
        tags: list[str] = None,
    ) -> list[Memory]:
        """
        Search memories using full-text search.
        Falls back to recency-ranked results if query is too short.
        """
        if len(query.strip()) < 3:
            return await self._get_recent(user_id=user_id, limit=limit)

        # FTS search
        rows = await self._db.execute_fetchall(
            """
            SELECT m.id, m.content, m.user_id, m.tags, m.created_at, m.accessed_at, m.access_count
            FROM memories m
            JOIN memories_fts fts ON fts.rowid = m.id
            WHERE memories_fts MATCH ? AND m.user_id = ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, user_id, limit)
        )

        memories = [self._row_to_memory(r) for r in rows]

        # Tag filter
        if tags:
            memories = [
                m for m in memories
                if any(t in m.tags for t in tags)
            ]

        # Update access stats
        for m in memories:
            await self._touch(m.id)

        return memories

    async def _get_recent(self, user_id: str, limit: int) -> list[Memory]:
        """Return most recently accessed memories."""
        rows = await self._db.execute_fetchall(
            """
            SELECT id, content, user_id, tags, created_at, accessed_at, access_count
            FROM memories
            WHERE user_id = ?
            ORDER BY accessed_at DESC
            LIMIT ?
            """,
            (user_id, limit)
        )
        return [self._row_to_memory(r) for r in rows]

    async def delete(self, memory_id: int):
        """Delete a specific memory by ID."""
        await self._db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        await self._db.execute("DELETE FROM memories_fts WHERE rowid = ?", (memory_id,))
        await self._db.commit()

    async def get_all(self, user_id: str = "default") -> list[Memory]:
        """Retrieve all memories for a user."""
        rows = await self._db.execute_fetchall(
            """
            SELECT id, content, user_id, tags, created_at, accessed_at, access_count
            FROM memories WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,)
        )
        return [self._row_to_memory(r) for r in rows]

    async def _touch(self, memory_id: int):
        """Update last accessed time and increment access counter."""
        now = datetime.utcnow().isoformat()
        await self._db.execute(
            "UPDATE memories SET accessed_at = ?, access_count = access_count + 1 WHERE id = ?",
            (now, memory_id)
        )
        await self._db.commit()

    def _row_to_memory(self, row) -> Memory:
        return Memory(
            id=row["id"],
            content=row["content"],
            user_id=row["user_id"],
            tags=json.loads(row["tags"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            accessed_at=datetime.fromisoformat(row["accessed_at"]),
            access_count=row["access_count"],
        )

    async def close(self):
        if self._db:
            await self._db.close()
            logger.info("Memory store closed")
