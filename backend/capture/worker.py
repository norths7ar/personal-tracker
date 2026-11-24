"""One bounded background parser per instance, with a durable SQLite work queue."""

import json
import logging
import math
import os
import threading

from backend.capture import queue
from backend.capture.batch import BatchExtractor
from backend.llm import LLMClient, LLMError
from backend.paths import database_path
from backend.settings.store import load_extraction_snapshot

logger = logging.getLogger(__name__)


class CaptureWorker:
    def __init__(self) -> None:
        self.database = database_path()
        self.stopping = threading.Event()
        self.thread: threading.Thread | None = None
        self.lock_file = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="capture-parser", daemon=True)
        self.thread.start()

    def _acquire_lock(self) -> bool:
        lock = self.database.with_name("capture-worker.lock").open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock.close()
            return False
        try:
            queue.recover_processing(self.database)
        except Exception:
            lock.close()
            raise
        self.lock_file = lock
        return True

    def stop(self) -> None:
        self.stopping.set()
        if self.thread is not None:
            self.thread.join(timeout=1)
        # A slow HTTP call may finish later. The daemon keeps its OS lock until
        # it exits and checks stopping before committing any parsed result.

    def _run(self) -> None:
        try:
            while not self.stopping.is_set():
                try:
                    if self.lock_file is None and not self._acquire_lock():
                        self.stopping.wait(0.5)
                        continue
                    if not self.run_once():
                        self.stopping.wait(0.5)
                except Exception:
                    logger.exception("Capture queue worker failed")
                    self.stopping.wait(1)
        finally:
            if self.lock_file is not None:
                self.lock_file.close()
                self.lock_file = None

    def run_once(self) -> bool:
        if self.stopping.is_set():
            return False
        item = queue.claim_next(self.database)
        if item is None:
            return False
        try:
            snapshot = load_extraction_snapshot()
            config = snapshot.extraction_config()
            with _CancellableClient(
                snapshot.llm, snapshot.api_key, stopping=self.stopping
            ) as client:
                result = BatchExtractor(config, client).extract(
                    item["source_text"], item["default_date"]
                )
            if item["record_json"]:
                previous = json.loads(item["record_json"])
                records = result.get("records") or []
                if len(records) != 1 or result.get("rejected_records"):
                    queue.fail(item, "单条重试未得到唯一结果，请直接编辑确认", self.database)
                    return True
                # A retry may enrich uncertain fields, not silently settle a
                # contradiction in the previously extracted payment or date.
                record = records[0]
                contradiction = any(
                    record.get(field) != previous[field] for field in ("record_type", "date")
                )
                previous_amount = previous.get("amount")
                if previous_amount is not None and previous_amount > 0:
                    amount = record.get("amount")
                    contradiction = contradiction or (
                        not isinstance(amount, (int, float))
                        or not math.isfinite(amount)
                        or round(amount, 2) != round(previous_amount, 2)
                    )
                if contradiction:
                    queue.fail(
                        item,
                        "重试结果与原条目的类型、金额或日期不一致，请直接编辑确认",
                        self.database,
                    )
                    return True
                record["description"] = previous["description"]
                for field in ("time", "meal_type", "notes"):
                    if previous.get(field):
                        record[field] = previous[field]
            if self.stopping.is_set():
                queue.fail(item, "解析被中断，原文已保留，请重试", self.database)
            else:
                queue.complete(item, result, config, self.database)
        except LLMError as exc:
            queue.fail(item, str(exc), self.database)
        except Exception:
            logger.exception("Capture item %s failed", item["id"])
            queue.fail(item, "解析失败，原文已保留，请检查模型设置后重试", self.database)
        return True


class _CancellableClient(LLMClient):
    def __init__(self, config, api_key, *, stopping: threading.Event):
        super().__init__(config, api_key)
        self.stopping = stopping

    def invoke(self, system_prompt: str, user_msg: str) -> dict:
        if self.stopping.is_set():
            raise LLMError("解析被中断，原文已保留，请重试")
        return super().invoke(system_prompt, user_msg)
