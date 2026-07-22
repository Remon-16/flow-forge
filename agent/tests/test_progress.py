"""Tests for ProgressTracker — shared batch progress tracking utility.
ProgressTracker 测试 — 共享批次进度跟踪工具。
"""

import pytest
from utils.progress import ProgressTracker


class TestProgressTrackerCounts:
    """计数属性测试 / Count properties tests."""

    def should_calculate_counts(self):
        """total=68, 3 completed IDs → completed=3, remaining=65."""
        tracker = ProgressTracker.from_existing(
            total=68, batch_size=10, completed_ids={"t1", "t2", "t3"})
        assert tracker.completed == 3
        assert tracker.remaining == 65
        assert tracker.is_done is False

    def should_be_done_when_all_completed(self):
        """所有 ID 完成 → is_done=True."""
        tracker = ProgressTracker.from_existing(
            total=5, batch_size=1, completed_ids={"a", "b", "c", "d", "e"})
        assert tracker.completed == 5
        assert tracker.remaining == 0
        assert tracker.is_done is True

    def should_handle_empty(self):
        """total=0, 空 ID 集合 → 各项为 0."""
        tracker = ProgressTracker(total=0, batch_size=1)
        assert tracker.completed == 0
        assert tracker.remaining == 0
        assert tracker.is_done is True

    def should_handle_more_ids_than_total(self):
        """completed_ids > total → 防御性处理."""
        tracker = ProgressTracker.from_existing(
            total=5, batch_size=10, completed_ids={"a", "b", "c", "d", "e", "f"})
        assert tracker.completed == 6
        assert tracker.remaining == 0  # 不小于 0
        assert tracker.is_done is True

    def should_mark_completed_updates_counts(self):
        """mark_completed 后计数更新."""
        tracker = ProgressTracker(total=10, batch_size=3)
        assert tracker.completed == 0
        tracker.mark_completed(["a", "b", "c"])
        assert tracker.completed == 3
        tracker.mark_completed(["d", "e"])
        assert tracker.completed == 5

    def should_mark_completed_is_idempotent(self):
        """重复标记已完成 ID 不影响计数."""
        tracker = ProgressTracker.from_existing(
            total=10, batch_size=3, completed_ids={"a", "b"})
        assert tracker.completed == 2
        tracker.mark_completed(["a", "b"])  # 重复标记
        assert tracker.completed == 2
        tracker.mark_completed(["a", "c"])
        assert tracker.completed == 3


class TestProgressTrackerIterBatches:
    """批次迭代测试 / Batch iteration tests."""

    def should_yield_all_when_none_completed(self):
        """无已完成项 → iter_batches 返回所有项."""
        all_items = [(str(i), f"item_{i}") for i in range(10)]
        tracker = ProgressTracker(total=10, batch_size=3)

        batches = list(tracker.iter_batches(all_items))
        # 10 items, batch_size=3 → ceil(10/3)=4 batches
        assert len(batches) == 4

        # 第一批: 3 items
        ids1, items1, idx1, total1 = batches[0]
        assert ids1 == ["0", "1", "2"]
        assert items1 == ["item_0", "item_1", "item_2"]
        assert idx1 == 1
        assert total1 == 4

        # 第二批: 3 items
        ids2, items2, idx2, total2 = batches[1]
        assert ids2 == ["3", "4", "5"]
        assert idx2 == 2

        # 第三批: 3 items
        ids3, items3, idx3, total3 = batches[2]
        assert ids3 == ["6", "7", "8"]
        assert idx3 == 3

        # 第四批: 1 item
        ids4, items4, idx4, total4 = batches[3]
        assert ids4 == ["9"]
        assert idx4 == 4

    def should_filter_completed_items(self):
        """10 items, 3 done → iter_batches 只返回 7 个未完成的."""
        all_items = [(str(i), f"item_{i}") for i in range(10)]
        tracker = ProgressTracker.from_existing(
            total=10, batch_size=5,
            completed_ids={"0", "2", "4"})

        batches = list(tracker.iter_batches(all_items))
        # 7 remaining, batch_size=5 → ceil(7/5)=2 batches
        assert len(batches) == 2

        # 第一批: 5 items (IDs 1,3,5,6,7)
        ids1, items1, idx1, _ = batches[0]
        assert ids1 == ["1", "3", "5", "6", "7"]

        # 第二批: 2 items (IDs 8,9)
        ids2, items2, idx2, _ = batches[1]
        assert ids2 == ["8", "9"]

    def should_skip_fully_done_batch(self):
        """全部已完成 → iter_batches 不 yield 任何内容."""
        all_items = [("a", 1), ("b", 2), ("c", 3)]
        tracker = ProgressTracker.from_existing(
            total=3, batch_size=2,
            completed_ids={"a", "b", "c"})

        batches = list(tracker.iter_batches(all_items))
        assert len(batches) == 0

    def should_handle_batch_size_negative(self):
        """batch_size=-1 → 剩余全部为一整批."""
        all_items = [(str(i), f"item_{i}") for i in range(10)]
        tracker = ProgressTracker.from_existing(
            total=10, batch_size=-1,
            completed_ids={"0", "1"})

        batches = list(tracker.iter_batches(all_items))
        assert len(batches) == 1
        ids, items, idx, total = batches[0]
        assert len(ids) == 8  # 10 - 2 done
        assert idx == 1
        assert total == 1

    def should_handle_empty_input(self):
        """空输入列表 → 不 yield."""
        tracker = ProgressTracker(total=0, batch_size=5)
        batches = list(tracker.iter_batches([]))
        assert len(batches) == 0

    def should_iterate_with_item_objects(self):
        """iter_batches 应能处理复杂对象."""
        all_items = [("id_a", {"name": "A"}), ("id_b", {"name": "B"}),
                      ("id_c", {"name": "C"})]
        tracker = ProgressTracker.from_existing(
            total=3, batch_size=1, completed_ids={"id_a"})

        batches = list(tracker.iter_batches(all_items))
        assert len(batches) == 2
        ids1, items1, _, _ = batches[0]
        assert ids1 == ["id_b"]
        assert items1 == [{"name": "B"}]

        ids2, items2, _, _ = batches[1]
        assert ids2 == ["id_c"]
        assert items2 == [{"name": "C"}]


class TestProgressTrackerSerialization:
    """序列化测试 / Serialization tests."""

    def should_roundtrip_to_dict(self):
        """to_dict() + from_dict() 一致性."""
        tracker = ProgressTracker.from_existing(
            total=100, batch_size=10,
            completed_ids={"a", "b", "c"})

        d = tracker.to_dict()
        assert d == {
            "total_items": 100,
            "completed_count": 3,
            "batch_size": 10,
            "status": "in_progress",
        }

        restored = ProgressTracker.from_dict(d, completed_ids={"a", "b", "c"})
        assert restored.total == 100
        assert restored.batch_size == 10
        assert restored.completed == 3

    def should_derive_completed_from_ids_not_old_counter(self):
        """旧的 completed_count=59, 但 ID 集合 = 61 → completed 应为 61（不信任旧计数器）."""
        old_dict = {
            "total_items": 68,
            "completed_count": 59,  # 过期值 / stale value
            "batch_size": 10,
            "status": "in_progress",
        }
        actual_ids = {f"t{i}" for i in range(61)}  # 实际 61 个

        tracker = ProgressTracker.from_dict(old_dict, completed_ids=actual_ids)
        assert tracker.completed == 61  # 从 ID 集合计算，不是 59
        assert tracker.total == 68

    def should_be_done_status_when_all_completed(self):
        """全部完成 → to_dict status='completed'."""
        tracker = ProgressTracker.from_existing(
            total=5, batch_size=5,
            completed_ids={"a", "b", "c", "d", "e"})
        d = tracker.to_dict()
        assert d["status"] == "completed"

    def should_roundtrip_lightweight(self):
        """to_lightweight_dict 兼容 plan_chunks_progress.json 格式."""
        tracker = ProgressTracker.from_existing(
            total=10, batch_size=1,
            completed_ids={"chunk_a", "chunk_b"})

        light = tracker.to_lightweight_dict()
        assert light["version"] == 2
        assert light["total_items"] == 10
        assert light["completed_count"] == 2
        assert sorted(light["completed_ids"]) == ["chunk_a", "chunk_b"]

    def should_empty_factory_create_tracker(self):
        """默认构造 — 无已完成 ID."""
        tracker = ProgressTracker(total=50, batch_size=5)
        assert tracker.completed == 0
        assert tracker.remaining == 50
        d = tracker.to_dict()
        assert d == {
            "total_items": 50,
            "completed_count": 0,
            "batch_size": 5,
            "status": "in_progress",
        }
