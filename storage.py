import base64
import datetime
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class StorageBackend:
    def get_settings(self, user_id: str = "default") -> Dict[str, Any]:
        raise NotImplementedError

    def get_raw_ai_config(self, user_id: str = "default") -> Tuple[str, bool]:
        raise NotImplementedError

    def update_settings(
        self,
        bmr: int,
        target_calories: int,
        use_ai: bool,
        gemini_api_key: Optional[str] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def list_meals(
        self,
        start_iso: Optional[str] = None,
        end_iso: Optional[str] = None,
        user_id: str = "default",
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def create_meal(
        self,
        meal_data: Dict[str, Any],
        image_data_url: str = "",
        user_id: str = "default",
    ) -> Dict[str, Any]:
        raise NotImplementedError

    def update_meal(
        self,
        meal_id: str,
        updates: Dict[str, Any],
        user_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def delete_meal(self, meal_id: str, user_id: str = "default") -> bool:
        raise NotImplementedError

    def read_image(self, blob_name: str, user_id: str = "default") -> Optional[Tuple[bytes, str]]:
        raise NotImplementedError


def _decode_data_url(data_url: str) -> Optional[Tuple[bytes, str, str]]:
    if not data_url or "," not in data_url:
        return None
    header, b64_data = data_url.split(",", 1)
    ext = ".jpg"
    mime = "image/jpeg"
    if "image/png" in header:
        ext = ".png"
        mime = "image/png"
    elif "image/webp" in header:
        ext = ".webp"
        mime = "image/webp"
    try:
        raw = base64.b64decode(b64_data)
    except Exception:
        return None
    if len(raw) > 2 * 1024 * 1024:
        return None
    return raw, ext, mime


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) >= 10:
        return key[:4] + "****" + key[-4:]
    return "****"


class SQLiteStorage(StorageBackend):
    def __init__(self, db_path: Path, upload_dir: Path) -> None:
        self.db_path = db_path
        self.upload_dir = upload_dir
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id TEXT PRIMARY KEY,
                    bmr INTEGER NOT NULL DEFAULT 1500,
                    target_calories INTEGER NOT NULL DEFAULT 1800,
                    gemini_api_key TEXT NOT NULL DEFAULT '',
                    use_ai INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meals (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    name TEXT NOT NULL,
                    eaten_at TEXT NOT NULL,
                    meal_type TEXT NOT NULL DEFAULT '昼食',
                    calories INTEGER NOT NULL,
                    protein REAL NOT NULL DEFAULT 0,
                    fat REAL NOT NULL DEFAULT 0,
                    carbs REAL NOT NULL DEFAULT 0,
                    source TEXT NOT NULL DEFAULT 'dictionary',
                    image_path TEXT NOT NULL DEFAULT '',
                    memo TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            # Migrate older single-user meals table if user_id column is missing
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(meals)").fetchall()]
            if "user_id" not in cols:
                conn.execute("ALTER TABLE meals ADD COLUMN user_id TEXT NOT NULL DEFAULT 'default'")

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_meals_user_eaten ON meals (user_id, eaten_at)"
            )
            conn.commit()

    def _ensure_user_settings(self, conn: sqlite3.Connection, user_id: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is not None:
            return row
        now = datetime.datetime.now().isoformat(timespec="seconds")
        conn.execute(
            """
            INSERT INTO user_settings (user_id, bmr, target_calories, gemini_api_key, use_ai, updated_at)
            VALUES (?, 1500, 1800, '', 0, ?)
            """,
            (user_id, now),
        )
        conn.commit()
        return conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()

    def get_settings(self, user_id: str = "default") -> Dict[str, Any]:
        with self._conn() as conn:
            row = self._ensure_user_settings(conn, user_id)
        key = row["gemini_api_key"] or ""
        return {
            "bmr": int(row["bmr"]),
            "target_calories": int(row["target_calories"]),
            "has_gemini_key": bool(key),
            "gemini_api_key_masked": _mask_key(key),
            "use_ai": bool(row["use_ai"]),
        }

    def get_raw_ai_config(self, user_id: str = "default") -> Tuple[str, bool]:
        with self._conn() as conn:
            row = self._ensure_user_settings(conn, user_id)
        return str(row["gemini_api_key"] or ""), bool(row["use_ai"])

    def update_settings(
        self,
        bmr: int,
        target_calories: int,
        use_ai: bool,
        gemini_api_key: Optional[str] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        now = datetime.datetime.now().isoformat(timespec="seconds")
        use_ai_int = 1 if use_ai else 0
        with self._conn() as conn:
            self._ensure_user_settings(conn, user_id)
            if gemini_api_key is not None:
                conn.execute(
                    """
                    UPDATE user_settings
                    SET bmr = ?, target_calories = ?, gemini_api_key = ?, use_ai = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (bmr, target_calories, gemini_api_key.strip(), use_ai_int, now, user_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE user_settings
                    SET bmr = ?, target_calories = ?, use_ai = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (bmr, target_calories, use_ai_int, now, user_id),
                )
            conn.commit()
        return self.get_settings(user_id)

    def list_meals(
        self,
        start_iso: Optional[str] = None,
        end_iso: Optional[str] = None,
        user_id: str = "default",
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            if start_iso and end_iso:
                rows = conn.execute(
                    "SELECT * FROM meals WHERE user_id = ? AND eaten_at >= ? AND eaten_at <= ? ORDER BY eaten_at ASC",
                    (user_id, start_iso, end_iso),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM meals WHERE user_id = ? ORDER BY eaten_at DESC LIMIT 100",
                    (user_id,),
                ).fetchall()
        return [dict(r) for r in rows]

    def create_meal(
        self,
        meal_data: Dict[str, Any],
        image_data_url: str = "",
        user_id: str = "default",
    ) -> Dict[str, Any]:
        meal_id = uuid.uuid4().hex[:12]
        created_at = datetime.datetime.now().isoformat(timespec="seconds")
        image_path = ""
        decoded = _decode_data_url(image_data_url)
        if decoded is not None:
            raw, ext, _ = decoded
            user_dir = self.upload_dir / Path(user_id).name
            user_dir.mkdir(parents=True, exist_ok=True)
            filename = f"{meal_id}{ext}"
            (user_dir / filename).write_bytes(raw)
            image_path = f"/api/images/{filename}"

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO meals (id, user_id, name, eaten_at, meal_type, calories, protein, fat, carbs, source, image_path, memo, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    meal_id,
                    user_id,
                    meal_data["name"],
                    meal_data["eaten_at"],
                    meal_data["meal_type"],
                    meal_data["calories"],
                    meal_data["protein"],
                    meal_data["fat"],
                    meal_data["carbs"],
                    meal_data["source"],
                    image_path,
                    meal_data["memo"],
                    created_at,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM meals WHERE id = ?", (meal_id,)).fetchone()
        return dict(row)

    def update_meal(
        self,
        meal_id: str,
        updates: Dict[str, Any],
        user_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM meals WHERE id = ? AND user_id = ?", (meal_id, user_id)
            ).fetchone()
            if existing is None:
                return None
            name = str(updates.get("name", existing["name"])).strip() or existing["name"]
            eaten_at = str(updates.get("eaten_at", existing["eaten_at"])).strip() or existing["eaten_at"]
            meal_type = str(updates.get("meal_type", existing["meal_type"]))
            calories = max(0, int(round(float(updates.get("calories", existing["calories"])))))
            protein = max(0.0, round(float(updates.get("protein", existing["protein"])), 1))
            fat = max(0.0, round(float(updates.get("fat", existing["fat"])), 1))
            carbs = max(0.0, round(float(updates.get("carbs", existing["carbs"])), 1))
            memo = str(updates.get("memo", existing["memo"]))
            conn.execute(
                """
                UPDATE meals
                SET name = ?, eaten_at = ?, meal_type = ?, calories = ?, protein = ?, fat = ?, carbs = ?, memo = ?
                WHERE id = ? AND user_id = ?
                """,
                (name, eaten_at, meal_type, calories, protein, fat, carbs, memo, meal_id, user_id),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM meals WHERE id = ? AND user_id = ?", (meal_id, user_id)
            ).fetchone()
        return dict(row)

    def delete_meal(self, meal_id: str, user_id: str = "default") -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT image_path FROM meals WHERE id = ? AND user_id = ?", (meal_id, user_id)
            ).fetchone()
            if row is None:
                return False
            img_path = row["image_path"]
            conn.execute("DELETE FROM meals WHERE id = ? AND user_id = ?", (meal_id, user_id))
            conn.commit()
        if img_path and img_path.startswith("/api/images/"):
            fname = Path(img_path[len("/api/images/"):]).name
            user_dir = (self.upload_dir / Path(user_id).name).resolve()
            f = (user_dir / fname).resolve()
            if user_dir in f.parents and f.exists():
                f.unlink()
        return True

    def read_image(self, blob_name: str, user_id: str = "default") -> Optional[Tuple[bytes, str]]:
        user_dir = (self.upload_dir / Path(user_id).name).resolve()
        safe = (user_dir / Path(blob_name).name).resolve()
        if user_dir not in safe.parents or not safe.exists():
            return None
        ext = safe.suffix.lower()
        mime = "image/png" if ext == ".png" else ("image/webp" if ext == ".webp" else "image/jpeg")
        return safe.read_bytes(), mime


class FirestoreGCSStorage(StorageBackend):
    """
    GCP Native Backend (Multi-user isolated):
    - Firestore: cal_snap_users/{user_id} (settings) & cal_snap_users/{user_id}/meals/{meal_id}
    - Cloud Storage: meals/{user_id}/{meal_id}.jpg
    """

    def __init__(self, project_id: Optional[str], bucket_name: str) -> None:
        from google.cloud import firestore, storage  # type: ignore

        self.db = firestore.Client(project=project_id) if project_id else firestore.Client()
        self.gcs_client = storage.Client(project=project_id) if project_id else storage.Client()
        self.bucket = self.gcs_client.bucket(bucket_name) if bucket_name else None
        self.users_col = self.db.collection("cal_snap_users")

    def _user_doc_ref(self, user_id: str):
        return self.users_col.document(user_id)

    def _meals_col(self, user_id: str):
        return self._user_doc_ref(user_id).collection("meals")

    def _ensure_settings_doc(self, user_id: str) -> Dict[str, Any]:
        ref = self._user_doc_ref(user_id)
        snap = ref.get()
        if snap.exists:
            return snap.to_dict() or {}
        default_doc = {
            "bmr": 1500,
            "target_calories": 1800,
            "gemini_api_key": "",
            "use_ai": False,
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        ref.set(default_doc)
        return default_doc

    def get_settings(self, user_id: str = "default") -> Dict[str, Any]:
        doc = self._ensure_settings_doc(user_id)
        key = str(doc.get("gemini_api_key", "") or "")
        return {
            "bmr": int(doc.get("bmr", 1500)),
            "target_calories": int(doc.get("target_calories", 1800)),
            "has_gemini_key": bool(key),
            "gemini_api_key_masked": _mask_key(key),
            "use_ai": bool(doc.get("use_ai", False)),
        }

    def get_raw_ai_config(self, user_id: str = "default") -> Tuple[str, bool]:
        doc = self._ensure_settings_doc(user_id)
        return str(doc.get("gemini_api_key", "") or ""), bool(doc.get("use_ai", False))

    def update_settings(
        self,
        bmr: int,
        target_calories: int,
        use_ai: bool,
        gemini_api_key: Optional[str] = None,
        user_id: str = "default",
    ) -> Dict[str, Any]:
        self._ensure_settings_doc(user_id)
        updates: Dict[str, Any] = {
            "bmr": bmr,
            "target_calories": target_calories,
            "use_ai": bool(use_ai),
            "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        if gemini_api_key is not None:
            updates["gemini_api_key"] = gemini_api_key.strip()
        self._user_doc_ref(user_id).update(updates)
        return self.get_settings(user_id)

    def list_meals(
        self,
        start_iso: Optional[str] = None,
        end_iso: Optional[str] = None,
        user_id: str = "default",
    ) -> List[Dict[str, Any]]:
        col = self._meals_col(user_id)
        if start_iso and end_iso:
            query = (
                col
                .where("eaten_at", ">=", start_iso)
                .where("eaten_at", "<=", end_iso)
                .order_by("eaten_at")
            )
            return [d.to_dict() for d in query.stream()]
        docs = col.order_by("eaten_at", direction="DESCENDING").limit(100).stream()
        return [d.to_dict() for d in docs]

    def create_meal(
        self,
        meal_data: Dict[str, Any],
        image_data_url: str = "",
        user_id: str = "default",
    ) -> Dict[str, Any]:
        meal_id = uuid.uuid4().hex[:12]
        created_at = datetime.datetime.now().isoformat(timespec="seconds")
        image_path = ""

        decoded = _decode_data_url(image_data_url)
        if decoded is not None and self.bucket is not None:
            raw, ext, mime = decoded
            blob_name = f"{meal_id}{ext}"
            blob = self.bucket.blob(f"meals/{user_id}/{blob_name}")
            blob.upload_from_string(raw, content_type=mime)
            image_path = f"/api/images/{blob_name}"

        doc = {
            "id": meal_id,
            "user_id": user_id,
            "name": meal_data["name"],
            "eaten_at": meal_data["eaten_at"],
            "meal_type": meal_data["meal_type"],
            "calories": meal_data["calories"],
            "protein": meal_data["protein"],
            "fat": meal_data["fat"],
            "carbs": meal_data["carbs"],
            "source": meal_data["source"],
            "image_path": image_path,
            "memo": meal_data["memo"],
            "created_at": created_at,
        }
        self._meals_col(user_id).document(meal_id).set(doc)
        return doc

    def update_meal(
        self,
        meal_id: str,
        updates: Dict[str, Any],
        user_id: str = "default",
    ) -> Optional[Dict[str, Any]]:
        ref = self._meals_col(user_id).document(meal_id)
        snap = ref.get()
        if not snap.exists:
            return None
        existing = snap.to_dict() or {}
        new_data = {
            "name": str(updates.get("name", existing.get("name", ""))).strip() or existing.get("name", "食事"),
            "eaten_at": str(updates.get("eaten_at", existing.get("eaten_at", ""))).strip() or existing.get("eaten_at", ""),
            "meal_type": str(updates.get("meal_type", existing.get("meal_type", "昼食"))),
            "calories": max(0, int(round(float(updates.get("calories", existing.get("calories", 0)))))),
            "protein": max(0.0, round(float(updates.get("protein", existing.get("protein", 0))), 1)),
            "fat": max(0.0, round(float(updates.get("fat", existing.get("fat", 0))), 1)),
            "carbs": max(0.0, round(float(updates.get("carbs", existing.get("carbs", 0))), 1)),
            "memo": str(updates.get("memo", existing.get("memo", ""))),
        }
        ref.update(new_data)
        return ref.get().to_dict()

    def delete_meal(self, meal_id: str, user_id: str = "default") -> bool:
        ref = self._meals_col(user_id).document(meal_id)
        snap = ref.get()
        if not snap.exists:
            return False
        doc = snap.to_dict() or {}
        img_path = str(doc.get("image_path", ""))
        ref.delete()
        if img_path.startswith("/api/images/") and self.bucket is not None:
            blob_name = Path(img_path[len("/api/images/"):]).name
            blob = self.bucket.blob(f"meals/{user_id}/{blob_name}")
            if blob.exists():
                blob.delete()
        return True

    def read_image(self, blob_name: str, user_id: str = "default") -> Optional[Tuple[bytes, str]]:
        if self.bucket is None:
            return None
        safe_name = Path(blob_name).name
        blob = self.bucket.blob(f"meals/{user_id}/{safe_name}")
        if not blob.exists():
            return None
        data = blob.download_as_bytes()
        mime = blob.content_type or "image/jpeg"
        return data, mime


def create_storage(base_dir: Path) -> StorageBackend:
    backend = os.environ.get("STORAGE_BACKEND", "sqlite").strip().lower()
    if backend == "gcp":
        project_id = os.environ.get("FIRESTORE_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        bucket_name = os.environ.get("GCS_BUCKET", "").strip()
        return FirestoreGCSStorage(project_id=project_id, bucket_name=bucket_name)
    return SQLiteStorage(
        db_path=base_dir / "data" / "cal_snap.db",
        upload_dir=base_dir / "data" / "uploads",
    )
