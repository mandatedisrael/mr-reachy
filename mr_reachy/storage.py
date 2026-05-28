"""Medication memory storage for Sam.

Local JSON is the fast operational cache. 0G Storage is best-effort durable
sync; failures must never block medication reminders.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path

from .config import StorageConfig
from .medication import MedicationMemory, _now_iso


class LocalMedicationStore:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path).expanduser()

    def load(self) -> MedicationMemory:
        if not self.path.exists():
            return MedicationMemory()
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return MedicationMemory()
        return MedicationMemory.from_dict(data)

    def save(self, memory: MedicationMemory) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".sam-memory-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(memory.to_dict(), fh, indent=2, sort_keys=True)
                fh.write("\n")
            os.replace(temp_path, self.path)
        except Exception:
            try:
                os.remove(temp_path)
            except OSError:
                pass
            raise


class OGStorageMedicationStore:
    def __init__(self, config: StorageConfig):
        self.config = config
        self.last_error: str | None = None

    @property
    def enabled(self) -> bool:
        return self.config.og_ready

    def load(self) -> MedicationMemory | None:
        if not self.enabled or not self.config.memory_root:
            return None
        try:
            from core.indexer import Indexer
        except Exception as exc:
            self.last_error = f"0G Storage SDK unavailable: {exc}"
            return None

        fd, path = tempfile.mkstemp(prefix="sam-memory-", suffix=".json")
        os.close(fd)
        try:
            indexer = Indexer(self.config.indexer_url)
            try:
                err = indexer.download(self.config.memory_root, path, proof=False)
            except TypeError:
                err = indexer.download(self.config.memory_root, path)
            if err is not None:
                self.last_error = f"0G Storage download failed: {err}"
                return None
            with open(path, "r", encoding="utf-8") as fh:
                return MedicationMemory.from_dict(json.load(fh))
        except Exception as exc:
            self.last_error = f"0G Storage download failed: {exc}"
            return None
        finally:
            try:
                os.remove(path)
            except OSError:
                pass

    def save(self, memory: MedicationMemory) -> str | None:
        if not self.enabled:
            return None
        try:
            from core.file import ZgFile
            from core.indexer import Indexer
            from eth_account import Account
        except Exception as exc:
            self.last_error = f"0G Storage SDK unavailable: {exc}"
            return None

        fd, path = tempfile.mkstemp(prefix="sam-memory-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(memory.to_dict(), fh, indent=2, sort_keys=True)
                fh.write("\n")

            account = Account.from_key(self.config.private_key)
            indexer = Indexer(self.config.indexer_url)
            zg_file = ZgFile.from_file_path(path)
            try:
                result, err = indexer.upload(
                    zg_file,
                    self.config.rpc_url,
                    account,
                    {
                        "tags": b"\x00",
                        "finalityRequired": True,
                        "expectedReplica": 1,
                        "account": account,
                    },
                )
            finally:
                try:
                    zg_file.close()
                except Exception:
                    pass
            if err is not None:
                self.last_error = f"0G Storage upload failed: {err}"
                return None
            root = str((result or {}).get("rootHash") or "")
            if root:
                self.last_error = None
                return root
            self.last_error = "0G Storage upload returned no rootHash."
            return None
        except Exception as exc:
            self.last_error = f"0G Storage upload failed: {exc}"
            return None
        finally:
            try:
                os.remove(path)
            except OSError:
                pass


class HybridMedicationStore:
    def __init__(
        self,
        local: LocalMedicationStore,
        og: OGStorageMedicationStore | None = None,
        *,
        auto_sync: bool = True,
    ):
        self.local = local
        self.og = og
        self.auto_sync = auto_sync
        self._sync_lock = threading.Lock()

    def load(self) -> MedicationMemory:
        memory = self.local.load()
        if memory.plans or self.og is None:
            if memory.pending_sync and self.auto_sync:
                self.sync_pending_async()
            return memory
        synced = self.og.load()
        if synced is not None:
            synced.pending_sync = False
            synced.last_sync_error = None
            synced.last_synced_at = _now_iso()
            self.local.save(synced)
            return synced
        return memory

    def save(self, memory: MedicationMemory) -> MedicationMemory:
        memory.updated_at = _now_iso()
        memory.pending_sync = True
        self.local.save(memory)
        if self.auto_sync:
            self.sync_pending_async()
        return memory

    def sync_pending_async(self) -> None:
        if self.og is None:
            return
        threading.Thread(target=self.sync_pending, daemon=True).start()

    def sync_pending(self) -> MedicationMemory:
        with self._sync_lock:
            memory = self.local.load()
            if not memory.pending_sync or self.og is None:
                return memory
            root = self.og.save(memory)
            if root:
                memory.og_storage_root = root
                memory.pending_sync = False
                memory.last_synced_at = _now_iso()
                memory.last_sync_error = None
            else:
                memory.pending_sync = True
                memory.last_sync_error = getattr(self.og, "last_error", None) or "0G Storage sync did not complete."
            self.local.save(memory)
            return memory


def build_medication_store(config: StorageConfig) -> HybridMedicationStore:
    local = LocalMedicationStore(config.memory_path)
    og = OGStorageMedicationStore(config) if config.enabled else None
    return HybridMedicationStore(local, og)
