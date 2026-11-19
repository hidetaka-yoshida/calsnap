import base64
import calendar
import datetime
import hashlib
import hmac
import http.cookies
import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from estimator import (
    estimate_from_image_heuristic,
    estimate_from_text,
    estimate_with_gemini,
)
from storage import StorageBackend, create_storage

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"


def judge_day(calories: int, bmr: int, target_calories: int) -> Dict[str, Any]:
    """Judge daily calorie intake against BMR (基礎代謝量) and target calories."""
    effective_target = max(target_calories, bmr)
    if calories <= 0:
        return {
            "status": "no_data",
            "label": "記録なし",
            "color": "gray",
            "detail": "食事がまだ記録されていません。",
        }
    if calories < int(bmr * 0.85):
        return {
            "status": "too_low",
            "label": "基礎代謝を大幅下回り",
            "color": "blue",
            "detail": f"基礎代謝量（{bmr} kcal）を大きく下回っています。栄養不足に注意してください。",
        }
    if calories < bmr:
        return {
            "status": "below_bmr",
            "label": "基礎代謝未満",
            "color": "amber",
            "detail": f"基礎代謝量（{bmr} kcal）をやや下回っています。あと {bmr - calories} kcal 以上の摂取が望ましいです。",
        }
    if calories <= effective_target:
        return {
            "status": "good",
            "label": "良好（適正）",
            "color": "green",
            "detail": f"基礎代謝量（{bmr} kcal）〜目標（{effective_target} kcal）の適正範囲内です。",
        }
    if calories <= int(effective_target * 1.15):
        return {
            "status": "slightly_over",
            "label": "やや超過",
            "color": "orange",
            "detail": f"目標（{effective_target} kcal）を {calories - effective_target} kcal 超過しています。",
        }
    return {
        "status": "over",
        "label": "超過",
        "color": "red",
        "detail": f"目標（{effective_target} kcal）を {calories - effective_target} kcal 大幅に超過しています。",
    }


def compute_summary(
    storage: StorageBackend,
    period: str,
    date_str: str,
    user_id: str = "default",
) -> Dict[str, Any]:
    try:
        ref_date = datetime.date.fromisoformat(date_str)
    except ValueError:
        ref_date = datetime.date.today()

    settings = storage.get_settings(user_id=user_id)
    bmr = settings["bmr"]
    target = settings["target_calories"]

    if period == "week":
        start_date = ref_date - datetime.timedelta(days=ref_date.weekday())
        end_date = start_date + datetime.timedelta(days=6)
    elif period == "month":
        start_date = ref_date.replace(day=1)
        last_day = calendar.monthrange(ref_date.year, ref_date.month)[1]
        end_date = ref_date.replace(day=last_day)
    else:
        period = "day"
        start_date = ref_date
        end_date = ref_date

    start_iso = f"{start_date.isoformat()}T00:00:00"
    end_iso = f"{end_date.isoformat()}T23:59:59"

    meals = storage.list_meals(start_iso, end_iso, user_id=user_id)

    daily_map: Dict[str, Dict[str, Any]] = {}
    cur = start_date
    while cur <= end_date:
        d_iso = cur.isoformat()
        daily_map[d_iso] = {
            "date": d_iso,
            "label": f"{cur.month}/{cur.day}",
            "calories": 0,
            "protein": 0.0,
            "fat": 0.0,
            "carbs": 0.0,
            "count": 0,
        }
        cur += datetime.timedelta(days=1)

    total_cal = 0
    total_p = 0.0
    total_f = 0.0
    total_c = 0.0

    for m in meals:
        d_key = str(m["eaten_at"])[:10]
        cal = int(m["calories"])
        p = float(m["protein"])
        f = float(m["fat"])
        c = float(m["carbs"])
        total_cal += cal
        total_p += p
        total_f += f
        total_c += c
        if d_key in daily_map:
            daily_map[d_key]["calories"] += cal
            daily_map[d_key]["protein"] = round(daily_map[d_key]["protein"] + p, 1)
            daily_map[d_key]["fat"] = round(daily_map[d_key]["fat"] + f, 1)
            daily_map[d_key]["carbs"] = round(daily_map[d_key]["carbs"] + c, 1)
            daily_map[d_key]["count"] += 1

    days_list: List[Dict[str, Any]] = []
    recorded_days = 0
    good_days = 0
    for d_iso in sorted(daily_map.keys()):
        entry = daily_map[d_iso]
        j = judge_day(entry["calories"], bmr, target)
        entry["judgment"] = j
        if entry["count"] > 0:
            recorded_days += 1
            if j["status"] == "good":
                good_days += 1
        days_list.append(entry)

    avg_calories = round(total_cal / recorded_days) if recorded_days > 0 else 0
    day_judgment = (
        judge_day(total_cal, bmr, target)
        if period == "day"
        else judge_day(avg_calories, bmr, target)
    )

    return {
        "period": period,
        "date": ref_date.isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "bmr": bmr,
        "target_calories": target,
        "total_calories": total_cal,
        "average_calories": avg_calories,
        "recorded_days": recorded_days,
        "total_days": len(days_list),
        "good_days": good_days,
        "protein": round(total_p, 1),
        "fat": round(total_f, 1),
        "carbs": round(total_c, 1),
        "judgment": day_judgment,
        "days": days_list,
        "meals": meals,
    }


def _sign_session(payload: Dict[str, Any], secret: str) -> str:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii")
    sig = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def _verify_session(token: str, secret: str) -> Optional[Dict[str, Any]]:
    if not token or "." not in token:
        return None
    b64, sig = token.rsplit(".", 1)
    expected = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(b64.encode("ascii")).decode("utf-8"))
        if int(data.get("exp", 0)) < int(time.time()):
            return None
        return data
    except Exception:
        return None


def verify_google_id_token(id_token: str, expected_client_id: str) -> Optional[Dict[str, str]]:
    """Verify Google Identity Services ID token via Google's tokeninfo endpoint."""
    if not id_token or not expected_client_id:
        return None
    url = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token)}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            info = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None

    if info.get("aud") != expected_client_id:
        return None
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        return None
    if str(info.get("email_verified", "")).lower() != "true":
        return None
    sub = str(info.get("sub", "")).strip()
    email = str(info.get("email", "")).strip().lower()
    if not sub or not email:
        return None
    return {
        "uid": f"google_{sub}",
        "email": email,
        "name": str(info.get("name") or email.split("@")[0]),
    }


class DietHandler(BaseHTTPRequestHandler):
    storage: StorageBackend
    passcode: str = ""
    google_client_id: str = ""
    allowed_emails: Set[str] = set()
    session_secret: str = ""

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _auth_mode(self) -> str:
        if self.google_client_id:
            return "google"
        if self.passcode:
            return "passcode"
        return "none"

    def _current_user(self) -> Optional[Dict[str, Any]]:
        mode = self._auth_mode()
        if mode == "none":
            return {"uid": "default", "email": "", "name": "ローカルユーザー"}
        raw_cookie = self.headers.get("Cookie", "")
        if not raw_cookie:
            return None
        token = None
        for part in raw_cookie.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                if k.strip() == "cal_snap_session":
                    token = v.strip().strip('"')
                    break
        if not token:
            return None
        session = _verify_session(token, self.session_secret)
        if session is None:
            return None
        if mode == "google" and not str(session.get("uid", "")).startswith("google_"):
            return None
        return session

    def _require_user(self) -> Optional[Dict[str, Any]]:
        user = self._current_user()
        if user is not None:
            return user
        self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Authentication required"})
        return None

    def _send_json(self, status: int, data: Any, extra_headers: Optional[Dict[str, str]] = None) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def _serve_file(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        ctype, _ = mimetypes.guess_type(str(file_path))
        if not ctype:
            ctype = "application/octet-stream"
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header(
            "Content-Type",
            f"{ctype}; charset=utf-8" if ctype.startswith("text/") or ctype in ("application/javascript", "application/json") else ctype,
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/healthz":
            self._send_json(HTTPStatus.OK, {"status": "ok"})
            return

        if path == "/api/auth/status":
            mode = self._auth_mode()
            user = self._current_user()
            self._send_json(HTTPStatus.OK, {
                "auth_mode": mode,
                "auth_required": mode != "none",
                "authenticated": user is not None,
                "google_client_id": self.google_client_id if mode == "google" else "",
                "user": {
                    "uid": user["uid"],
                    "email": user.get("email", ""),
                    "name": user.get("name", ""),
                } if user else None,
            })
            return

        if path == "/api/settings":
            user = self._require_user()
            if not user:
                return
            self._send_json(HTTPStatus.OK, self.storage.get_settings(user_id=user["uid"]))
            return

        if path == "/api/summary":
            user = self._require_user()
            if not user:
                return
            period = qs.get("period", ["day"])[0]
            date_str = qs.get("date", [datetime.date.today().isoformat()])[0]
            summary = compute_summary(self.storage, period, date_str, user_id=user["uid"])
            self._send_json(HTTPStatus.OK, summary)
            return

        if path == "/api/meals":
            user = self._require_user()
            if not user:
                return
            start = qs.get("start", [""])[0]
            end = qs.get("end", [""])[0]
            start_iso = f"{start}T00:00:00" if start else None
            end_iso = f"{end}T23:59:59" if end else None
            meals = self.storage.list_meals(start_iso, end_iso, user_id=user["uid"])
            self._send_json(HTTPStatus.OK, {"meals": meals})
            return

        if path.startswith("/api/images/"):
            user = self._require_user()
            if not user:
                return
            blob_name = path[len("/api/images/"):]
            img = self.storage.read_image(blob_name, user_id=user["uid"])
            if img is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            data, mime = img
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return

        # Serve static frontend
        if path == "/":
            self._serve_file(PUBLIC_DIR / "index.html")
            return
        rel_static = path.lstrip("/")
        safe_static = (PUBLIC_DIR / rel_static).resolve()
        if PUBLIC_DIR.resolve() in safe_static.parents:
            self._serve_file(safe_static)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        if path == "/api/auth/google":
            if not self.google_client_id:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Google Sign-In is not configured"})
                return
            id_token = str(body.get("id_token", "")).strip()
            user_info = verify_google_id_token(id_token, self.google_client_id)
            if user_info is None:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "Googleアカウントの認証に失敗しました"})
                return
            if self.allowed_emails and user_info["email"] not in self.allowed_emails:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "このアカウントは利用許可リストに含まれていません"})
                return
            session_payload = {
                "uid": user_info["uid"],
                "email": user_info["email"],
                "name": user_info["name"],
                "exp": int(time.time()) + 2592000,
            }
            token = _sign_session(session_payload, self.session_secret)
            cookie_val = f"cal_snap_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"
            self._send_json(HTTPStatus.OK, {"authenticated": True, "user": user_info}, {"Set-Cookie": cookie_val})
            return

        if path == "/api/auth/login":
            if not self.passcode:
                self._send_json(HTTPStatus.OK, {"authenticated": True})
                return
            attempt = str(body.get("passcode", ""))
            if hmac.compare_digest(attempt, self.passcode):
                session_payload = {
                    "uid": "default",
                    "email": "",
                    "name": "オーナー",
                    "exp": int(time.time()) + 2592000,
                }
                token = _sign_session(session_payload, self.session_secret)
                cookie_val = f"cal_snap_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000"
                self._send_json(HTTPStatus.OK, {"authenticated": True}, {"Set-Cookie": cookie_val})
            else:
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "パスコードが違います"})
            return

        if path == "/api/auth/logout":
            self._send_json(
                HTTPStatus.OK,
                {"authenticated": False},
                {"Set-Cookie": "cal_snap_session=; Path=/; HttpOnly; Max-Age=0"},
            )
            return

        user = self._require_user()
        if not user:
            return

        if path == "/api/estimate":
            query = str(body.get("query", "")).strip()
            portion = str(body.get("portion", "normal"))
            image_data_url = str(body.get("image_data_url", ""))
            filename = str(body.get("filename", ""))
            color_profile = body.get("color_profile")
            force_local = bool(body.get("force_local", False))

            api_key, use_ai = self.storage.get_raw_ai_config(user_id=user["uid"])

            if use_ai and api_key and not force_local:
                ai_res = estimate_with_gemini(
                    api_key=api_key,
                    query=query,
                    image_data_url=image_data_url,
                    portion=portion,
                )
                if ai_res is not None:
                    self._send_json(HTTPStatus.OK, ai_res)
                    return

            if image_data_url or color_profile:
                res = estimate_from_image_heuristic(
                    filename=filename,
                    hint_text=query,
                    color_profile=color_profile if isinstance(color_profile, dict) else None,
                    portion=portion,
                )
            else:
                res = estimate_from_text(query, portion=portion)

            self._send_json(HTTPStatus.OK, res)
            return

        if path == "/api/meals":
            eaten_at = str(body.get("eaten_at", "")).strip()
            if not eaten_at:
                eaten_at = datetime.datetime.now().isoformat(timespec="minutes")
            meal_data = {
                "name": str(body.get("name", "")).strip() or "食事",
                "eaten_at": eaten_at,
                "meal_type": str(body.get("meal_type", "昼食")),
                "calories": max(0, int(round(float(body.get("calories", 0))))),
                "protein": max(0.0, round(float(body.get("protein", 0)), 1)),
                "fat": max(0.0, round(float(body.get("fat", 0)), 1)),
                "carbs": max(0.0, round(float(body.get("carbs", 0)), 1)),
                "source": str(body.get("source", "dictionary")),
                "memo": str(body.get("memo", "")),
            }
            image_data_url = str(body.get("image_data_url", ""))
            created = self.storage.create_meal(meal_data, image_data_url=image_data_url, user_id=user["uid"])
            self._send_json(HTTPStatus.CREATED, {"meal": created})
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:
        user = self._require_user()
        if not user:
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        if path == "/api/settings":
            bmr = max(500, min(5000, int(round(float(body.get("bmr", 1500))))))
            target_calories = max(500, min(6000, int(round(float(body.get("target_calories", 1800))))))
            use_ai = bool(body.get("use_ai", False))
            new_key = str(body["gemini_api_key"]).strip() if body.get("gemini_api_key") is not None else None
            res = self.storage.update_settings(
                bmr=bmr,
                target_calories=target_calories,
                use_ai=use_ai,
                gemini_api_key=new_key,
                user_id=user["uid"],
            )
            self._send_json(HTTPStatus.OK, res)
            return

        if path.startswith("/api/meals/"):
            meal_id = path[len("/api/meals/"):]
            updated = self.storage.update_meal(meal_id, body, user_id=user["uid"])
            if updated is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Meal not found"})
                return
            self._send_json(HTTPStatus.OK, {"meal": updated})
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        user = self._require_user()
        if not user:
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/meals/"):
            meal_id = path[len("/api/meals/"):]
            deleted = self.storage.delete_meal(meal_id, user_id=user["uid"])
            if not deleted:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": "Meal not found"})
                return
            self._send_json(HTTPStatus.OK, {"deleted": meal_id})
            return

        self.send_error(HTTPStatus.NOT_FOUND)


def run_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    storage_backend = create_storage(BASE_DIR)
    passcode_val = os.environ.get("APP_PASSCODE", "").strip()
    google_cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    raw_allowed = os.environ.get("ALLOWED_EMAILS", "").strip()
    allowed_set = {e.strip().lower() for e in raw_allowed.split(",") if e.strip()}
    secret_val = (
        os.environ.get("SESSION_SECRET", "").strip()
        or f"cal_snap-{google_cid}-{passcode_val}-secret"
    )

    class ConfiguredHandler(DietHandler):
        pass

    ConfiguredHandler.storage = storage_backend
    ConfiguredHandler.passcode = passcode_val
    ConfiguredHandler.google_client_id = google_cid
    ConfiguredHandler.allowed_emails = allowed_set
    ConfiguredHandler.session_secret = secret_val

    server = ThreadingHTTPServer((host, port), ConfiguredHandler)
    print(f"CalSnap (かるスナップ) running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.server_close()


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    run_server(host=host, port=port)
