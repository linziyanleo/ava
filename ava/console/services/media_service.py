"""Media service: manage image generation records and files."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from ava.console.models import MediaRecord


_CHAT_UPLOAD_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_MAX_CHAT_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024


class MediaService:
    def __init__(
        self,
        media_dir: Path | None = None,
        db: Any | None = None,
        screenshot_dir: Path | None = None,
        chat_upload_dir: Path | None = None,
    ):
        self._media_dir = media_dir or (Path.home() / ".nanobot" / "media" / "generated")
        self._screenshot_dir = screenshot_dir or (self._media_dir.parent / "screenshots")
        self._chat_upload_dir = chat_upload_dir or (self._media_dir.parent / "chat-uploads")
        self._records_file = self._media_dir / "records.jsonl"
        self._db = db
        self._migrate_legacy_screenshots()

    @property
    def _use_db(self) -> bool:
        return self._db is not None

    def write_record(self, record: dict) -> None:
        """Write a media generation record (called from ImageGenTool)."""
        if self._use_db:
            self._db.execute(
                """INSERT OR REPLACE INTO media_records
                   (id, timestamp, prompt, reference_image, output_images, output_text, model, status, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.get("id", ""),
                    record.get("timestamp", ""),
                    record.get("prompt", ""),
                    record.get("reference_image"),
                    json.dumps(record.get("output_images", []), ensure_ascii=False),
                    record.get("output_text", ""),
                    record.get("model", ""),
                    record.get("status", "success"),
                    record.get("error"),
                ),
            )
            self._db.commit()
            return

        try:
            self._media_dir.mkdir(parents=True, exist_ok=True)
            with open(self._records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def query(
        self,
        page: int = 1,
        size: int = 20,
        search: str | None = None,
    ) -> dict[str, Any]:
        if self._use_db:
            return self._query_db(page, size, search)
        return self._query_jsonl(page, size, search)

    def _query_db(self, page: int, size: int, search: str | None) -> dict[str, Any]:
        if search:
            total_row = self._db.fetchone(
                "SELECT COUNT(*) as cnt FROM media_records WHERE prompt LIKE ?",
                (f"%{search}%",),
            )
            total = total_row["cnt"] if total_row else 0
            offset = (page - 1) * size
            rows = self._db.fetchall(
                """SELECT * FROM media_records WHERE prompt LIKE ?
                   ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
                (f"%{search}%", size, offset),
            )
        else:
            total_row = self._db.fetchone("SELECT COUNT(*) as cnt FROM media_records")
            total = total_row["cnt"] if total_row else 0
            offset = (page - 1) * size
            rows = self._db.fetchall(
                "SELECT * FROM media_records ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (size, offset),
            )

        records = []
        for r in rows:
            output_images = []
            if r["output_images"]:
                try:
                    output_images = json.loads(r["output_images"])
                except json.JSONDecodeError:
                    pass
            records.append(MediaRecord(
                id=r["id"],
                timestamp=r["timestamp"],
                prompt=r["prompt"],
                reference_image=r["reference_image"],
                output_images=output_images,
                output_text=r["output_text"] or "",
                model=r["model"] or "",
                status=r["status"] or "success",
                error=r["error"],
            ).model_dump())

        return {"records": records, "total": total, "page": page, "size": size}

    def _query_jsonl(self, page: int, size: int, search: str | None) -> dict[str, Any]:
        if not self._records_file.exists():
            return {"records": [], "total": 0, "page": page, "size": size}

        all_records: list[MediaRecord] = []
        for line in self._records_file.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = MediaRecord.model_validate_json(line)
                if search and search.lower() not in record.prompt.lower():
                    continue
                all_records.append(record)
            except Exception:
                continue

        all_records.reverse()
        total = len(all_records)
        start = (page - 1) * size
        end = start + size
        page_records = all_records[start:end]

        return {
            "records": [r.model_dump() for r in page_records],
            "total": total,
            "page": page,
            "size": size,
        }

    def _extract_filename(self, image_ref: str) -> str | None:
        normalized = image_ref.replace("\\", "/")
        filename = normalized.split("/")[-1]
        if not filename or filename in {".", ".."}:
            return None
        return filename

    @staticmethod
    def _safe_stem(name: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")
        return cleaned or "pasted-image"

    @staticmethod
    def build_display_path(image_ref: str) -> str:
        normalized = image_ref.replace("\\", "/")
        filename = normalized.split("/")[-1]
        if not filename:
            return "image"
        for marker in ("chat-uploads", "generated", "screenshots"):
            token = f"/{marker}/"
            if token in normalized:
                return f"{marker}/{filename}"
        return filename

    @staticmethod
    def build_preview_url(filename: str) -> str:
        return f"/api/media/images/{filename}"

    def save_chat_upload(self, *, filename: str | None, mime_type: str | None, data: bytes) -> dict[str, Any]:
        mime = (mime_type or "").lower().strip()
        if mime not in _CHAT_UPLOAD_MIME_EXTENSIONS:
            raise ValueError("Only PNG, JPEG, WEBP, and GIF images are supported")
        if not data:
            raise ValueError("Uploaded image is empty")
        if len(data) > _MAX_CHAT_UPLOAD_SIZE_BYTES:
            raise ValueError("Image exceeds 10MB limit")

        requested_name = filename or ""
        requested_suffix = Path(requested_name).suffix.lower()
        suffix = requested_suffix if requested_suffix in _CHAT_UPLOAD_MIME_EXTENSIONS.values() else _CHAT_UPLOAD_MIME_EXTENSIONS[mime]
        stem = self._safe_stem(Path(requested_name).stem or "pasted-image")
        stored_filename = f"chat-{uuid.uuid4().hex[:12]}-{stem}{suffix}"

        self._chat_upload_dir.mkdir(parents=True, exist_ok=True)
        stored_path = self._chat_upload_dir / stored_filename
        stored_path.write_bytes(data)

        return {
            "filename": stored_filename,
            "media_path": str(stored_path),
            "path": self.build_display_path(str(stored_path)),
            "mime_type": mime,
            "size_bytes": len(data),
            "preview_url": self.build_preview_url(stored_filename),
        }

    def _iter_lookup_paths(self, filename: str):
        seen: set[str] = set()
        for base_dir in (self._media_dir, self._screenshot_dir, self._chat_upload_dir):
            path = base_dir / filename
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            yield path

    def _iter_delete_paths(self, filename: str):
        seen: set[str] = set()
        for base_dir in (self._screenshot_dir, self._media_dir):
            path = base_dir / filename
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            yield path

    def _ensure_legacy_symlink(self, legacy_path: Path, target_path: Path) -> None:
        if not target_path.exists():
            return
        try:
            if legacy_path.is_symlink() and legacy_path.resolve(strict=False) == target_path.resolve(strict=False):
                return
        except OSError:
            pass

        try:
            if legacy_path.exists() or legacy_path.is_symlink():
                legacy_path.unlink()
            legacy_path.symlink_to(target_path)
        except Exception:
            pass

    def _migrate_legacy_screenshots(self) -> None:
        if self._screenshot_dir == self._media_dir or not self._media_dir.exists():
            return

        self._screenshot_dir.mkdir(parents=True, exist_ok=True)
        for legacy_path in sorted(self._media_dir.glob("page-agent-*.png")):
            target_path = self._screenshot_dir / legacy_path.name
            if legacy_path.is_symlink():
                self._ensure_legacy_symlink(legacy_path, target_path)
                continue
            if not legacy_path.is_file():
                continue

            try:
                if not target_path.exists():
                    legacy_path.replace(target_path)
                else:
                    legacy_path.unlink()
            except Exception:
                continue

            self._ensure_legacy_symlink(legacy_path, target_path)

    def _delete_output_images(self, image_refs: list[str]) -> None:
        for image_ref in image_refs:
            filename = self._extract_filename(image_ref)
            if not filename:
                continue
            for path in self._iter_delete_paths(filename):
                if not (path.exists() or path.is_symlink()):
                    continue
                try:
                    path.unlink()
                except Exception:
                    pass

    def get_image_path(self, filename: str) -> Path | None:
        if "/" in filename or "\\" in filename or ".." in filename:
            return None
        for path in self._iter_lookup_paths(filename):
            if path.is_file():
                return path
        return None

    def delete_record(self, record_id: str) -> bool:
        """Delete a media record and its associated image files.
        
        Returns True if deleted, raises ValueError if not found.
        """
        # Get record to find image paths
        if self._use_db:
            row = self._db.fetchone(
                "SELECT output_images FROM media_records WHERE id = ?",
                (record_id,),
            )
            if not row:
                raise ValueError(f"Record {record_id} not found")
            
            # Parse and delete image files
            output_images = []
            if row["output_images"]:
                try:
                    output_images = json.loads(row["output_images"])
                except json.JSONDecodeError:
                    pass
            
            self._delete_output_images(output_images)
            
            # Delete database record
            self._db.execute("DELETE FROM media_records WHERE id = ?", (record_id,))
            self._db.commit()
            return True
        
        # JSONL mode: rewrite file without the record
        if not self._records_file.exists():
            raise ValueError(f"Record {record_id} not found")
        
        lines = self._records_file.read_text("utf-8").splitlines()
        new_lines = []
        found = False
        deleted_images = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get("id") == record_id:
                    found = True
                    deleted_images = record.get("output_images", [])
                    continue
                new_lines.append(line)
            except json.JSONDecodeError:
                new_lines.append(line)
        
        if not found:
            raise ValueError(f"Record {record_id} not found")
        
        # Delete image files
        self._delete_output_images(deleted_images)
        
        # Rewrite records file
        self._records_file.write_text("\n".join(new_lines) + "\n" if new_lines else "", "utf-8")
        return True
