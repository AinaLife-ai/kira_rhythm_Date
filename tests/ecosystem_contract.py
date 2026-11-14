from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

from core.adapter.adapter_info import AdapterInfo
from core.chat import KiraIMMessage, KiraMessageBatchEvent, MessageChain, Session, User
from core.chat.message_elements import Text


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def batch(label: str, krd: bool):
    marker = {"run_id": f"run_{label}", "kind": "item", "persona_id": "persona-a", "item_id": f"item_{label}", "plan_id": "plan"} if krd else None
    message = KiraIMMessage(message_id=label, self_id="bot", timestamp=1,
        chain=MessageChain([Text(f"[生活节律｜系统触发]\n{label}")]), sender=User("system_krd" if krd else "user"),
        is_notice=krd, is_mentioned=True, extra={"krd": marker} if marker else None)
    return KiraMessageBatchEvent(supported_elements=["text"], timestamp=1,
        adapter=AdapterInfo(True, "qq", "qq", "QQ"), session=Session("qq", "dm", "10001"), messages=[message])


def main(s_root: Path, z_root: Path, memory_root: Path, daily_root: Path, accel_root: Path):
    for label, root in (("S", s_root), ("Z", z_root)):
        module = load(root / "queue_merge.py", f"queue_merge_{label}")
        merger = module.BatchMergeScheduler.__new__(module.BatchMergeScheduler)
        first, second = batch("schedule", True), batch("user", False)
        merged = merger._build_merged_batch([
            module.PendingBatch(time.time(), first), module.PendingBatch(time.time(), second)])
        assert len(merged.messages) == 2
        assert merged.messages[0] is first.messages[0]
        assert merged.messages[0].extra["krd"]["run_id"] == "run_schedule"
        assert merged.extra["_qm_self"] is True
        print(label, "MERGE CONTRACT OK")
    memory = (memory_root / "main.py").read_text()
    assert "if is_notice_message(message):" in memory
    assert "name=\"alife_memory\"" in memory and "persist=False" in memory
    daily = (daily_root / "main.py").read_text()
    assert "忽略第三方插件的合成通知消息" in daily
    accel = (accel_root / "stream_engine.py").read_text()
    assert "SegmentEmitter" in accel and "suppress" in accel
    print("MEMORY / DAILY / ACCEL CONTRACT OK")


if __name__ == "__main__":
    main(*(Path(value) for value in sys.argv[1:]))
