"""进度跟踪工具 — 跨阶段的批次进度计算与分批逻辑。
Progress tracker — shared batch progress arithmetic and splitting logic.

用于 plan 分块生成、skeleton 生成、插件执行三个阶段统一的进度管理。
Used by plan chunk generation, skeleton generation, and plugin execution
for consistent progress tracking and batch splitting.

核心设计 / Core design:
- completed 是 derived property，从 _completed_ids 集合计算，不是手动递增的整数
  这从根本上消除了 Bug 1（计数漂移）。
- completed is derived from the _completed_ids set, not a manually incremented
  integer. This eliminates Bug 1 (count drift) at the root.

- iter_batches() 自动过滤已完成 ID，不依赖 batch_size 计算跳过边界
  这从根本上消除了 Bug 2（batch_size 变化时跳过错误）。
- iter_batches() auto-filters completed IDs, independent of batch_size
  for skip-boundary calculation. This eliminates Bug 2 (incorrect skip
  when batch_size changes).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Set, Tuple


@dataclass
class ProgressTracker:
    """批次进度跟踪器 / Batch progress tracker.

    封装"共多少、完成多少、剩多少、如何分批"的通用逻辑。
    用于 plan 分块生成、skeleton 生成、插件执行三个阶段。
    Encapsulates common logic for total/remaining count and batch splitting.
    Used by plan chunk generation, skeleton generation, and plugin execution.

    Usage::

        # 方式 1：从已有 ID 列表构造 / From existing ID list
        tracker = ProgressTracker.from_existing(
            total=68, batch_size=10,
            completed_ids={"t1", "t2", "t3"},
        )
        assert tracker.completed == 3
        assert tracker.remaining == 65

        # 方式 2：空起点 / Fresh start
        tracker = ProgressTracker(total=68, batch_size=10)

        # 迭代剩余批次 / Iterate remaining batches
        for batch_ids, batch_items, batch_idx, total_batches \
                in tracker.iter_batches(all_items):
            process(batch_items)
            tracker.mark_completed(batch_ids)

        # 序列化到 checkpoint / Serialize for checkpoint
        d = tracker.to_dict()
        # => {"total_items":68, "completed_count":61, "batch_size":10, "status":"in_progress"}
    """

    total: int
    """总项数 / Total number of items."""

    batch_size: int = 1
    """每批处理的项数 / Items per batch. -1 表示一整批 / -1 means one batch."""

    _completed_ids: Set[str] = field(default_factory=set)
    """已完成的 ID 集合 / Set of completed item IDs."""

    # ------------------------------------------------------------------
    # 工厂方法 / Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_existing(
        cls,
        total: int,
        batch_size: int,
        completed_ids: Set[str],
    ) -> "ProgressTracker":
        """从已有已完成 ID 集合构造 / Construct from existing completed ID set.

        Args:
            total: 总项数 / Total number of items.
            batch_size: 批次大小 / Batch size.
            completed_ids: 已完成的 ID 集合 / Set of already-completed IDs.
        """
        return cls(
            total=total,
            batch_size=batch_size,
            _completed_ids=set(completed_ids),
        )

    # ------------------------------------------------------------------
    # 计数属性（只读，从 ID 集合计算，保证一致性）
    # Count properties (read-only, derived from ID set, guaranteed consistent)
    # ------------------------------------------------------------------

    @property
    def completed(self) -> int:
        """已完成数量（从 ID 集合计算，杜绝计数漂移）。
        Completed count — derived from ID set, eliminates count drift."""
        return len(self._completed_ids)

    @property
    def remaining(self) -> int:
        """剩余待处理数量 / Remaining items to process."""
        return max(0, self.total - self.completed)

    @property
    def is_done(self) -> bool:
        """是否全部完成 / Whether all items are done."""
        return self.completed >= self.total

    # ------------------------------------------------------------------
    # 批次迭代 / Batch iteration
    # ------------------------------------------------------------------

    def iter_batches(
        self,
        all_items: List[Tuple[str, Any]],
    ) -> Iterator[Tuple[List[str], List[Any], int, int]]:
        """迭代剩余批次 / Iterate remaining batches.

        自动过滤已完成的 item（by ID），仅返回未完成的批次。
        Automatically filters completed items (by ID), yields only pending batches.

        Args:
            all_items: (item_id, item) 元组列表（按处理顺序）。
                       List of (item_id, item) tuples in processing order.

        Yields:
            (batch_ids, batch_items, batch_idx_1based, total_batches):
            - batch_ids: 本批 item ID 列表（仅未完成的）
            - batch_items: 本批 item 列表（仅未完成的）
            - batch_idx: 1-based 批次索引
            - total_batches: 剩余总批次数
        """
        # 过滤已完成项 / Filter out completed items
        pending = [
            (iid, item) for iid, item in all_items
            if iid not in self._completed_ids
        ]
        if not pending:
            return

        bs = self.batch_size
        if bs < 1:
            bs = len(pending)
        total_batches = math.ceil(len(pending) / bs)

        for i in range(0, len(pending), bs):
            batch = pending[i:i + bs]
            ids = [iid for iid, _ in batch]
            items = [item for _, item in batch]
            yield ids, items, i // bs + 1, total_batches

    # ------------------------------------------------------------------
    # 标记完成 / Mark completion
    # ------------------------------------------------------------------

    def mark_completed(self, ids: List[str]) -> None:
        """标记一批 ID 为已完成 / Mark a batch of IDs as completed.

        幂等操作 — 重复标记已完成的 ID 不影响计数。
        Idempotent — re-marking already-completed IDs is harmless.
        """
        self._completed_ids.update(ids)

    # ------------------------------------------------------------------
    # 序列化 / Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 checkpoint phase_progress 格式。
        Serialize to checkpoint phase_progress format.

        输出兼容现有 checkpoint.json 中 phase_progress 的结构。
        Output is compatible with existing phase_progress structure in checkpoint.json.
        """
        return {
            "total_items": self.total,
            "completed_count": self.completed,
            "batch_size": self.batch_size,
            "status": "completed" if self.is_done else "in_progress",
        }

    @classmethod
    def from_dict(
        cls,
        d: Dict[str, Any],
        completed_ids: Set[str],
    ) -> "ProgressTracker":
        """从 checkpoint dict 恢复（不信任旧的 completed_count，从 ID 集合重算）。
        Restore from checkpoint dict — does NOT trust stale completed_count;
        recalculates from the provided ID set.

        Args:
            d: checkpoint 中的 phase_progress 条目。
               phase_progress entry from checkpoint.
            completed_ids: 已完成的 ID 集合（从实际数据中提取）。
                           Set of completed IDs (extracted from actual data).
        """
        return cls(
            total=d.get("total_items", 0),
            batch_size=d.get("batch_size", 1),
            _completed_ids=set(completed_ids),
        )

    def to_lightweight_dict(self) -> Dict[str, Any]:
        """序列化为 plan_chunks_progress.json 的 v2 轻量格式。
        Serialize to plan_chunks_progress.json v2 lightweight format.

        仅保存进度标记（ID 列表 + 计数），不保存内容。
        Only saves progress markers (ID list + counts), not content.
        """
        return {
            "version": 2,
            "completed_ids": sorted(self._completed_ids),
            "total_items": self.total,
            "completed_count": self.completed,
        }
