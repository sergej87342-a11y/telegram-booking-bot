"""
Flask API для сайта Telegram-бота записи.
Запуск локально:  python app.py
Документация:     http://localhost:5000/

Переменные окружения (читаются из os.environ):
  BOT_TOKEN      — токен от @BotFather (для отправки уведомления админу)
  ADMIN_CHAT_ID  — chat_id админа в Telegram
  PORT           — (опционально) порт, по умолчанию 5000

Файлы данных (общие с main.py):
  slots.json     — список слотов
  bookings.json  — список записей

Endpoints:
  GET  /        — список endpoint'ов
  GET  /slots   — JSON: только свободные слоты (status=free)
  POST /booking — создать запись (поля: name, phone, service, date, time)

main.py НЕ ТРОГАЕТСЯ. Этот файл — отдельный процесс, читает/пишет те же JSON.
"""
import json
import os
import re
from filelock import FileLock

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests


HERE = os.path.dirname(os.path.abspath(__file__))
SLOTS_PATH = os.path.join(HERE, "slots.json")
BOOKINGS_PATH = os.path.join(HERE, "bookings.json")
_SLOTS_LOCK = FileLock(SLOTS_PATH + ".lock")
_BOOKINGS_LOCK = FileLock(BOOKINGS_PATH + ".lock")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, ngrok-skip-browser-warning"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# ===== Файловые helpers (атомарная запись через tmp+replace) =====
_PHONE_RE = re.compile(r"^[\d\s\+\-\(\)]{7,20}$")


def _is_valid_phone(text):
    return bool(_PHONE_RE.match(text or ""))


def _norm(value):
    """Нормализация строк для сравнения: trim + lower-case. None → ''. """
    return str(value or "").strip().lower()


def _load_json_list(path):
    """Читает JSON. Поддерживает оба формата:
      - bare list: [...]
      - dict-обёртка: {"slots": [...]} или {"bookings": [...]} / {"items": [...]} / {"data": [...]}
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("slots", "bookings", "items", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _save_json_list(path, items):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_slots():
    return _load_json_list(SLOTS_PATH)


def save_slots(items):
    with _SLOTS_LOCK:
        _save_json_list(SLOTS_PATH, items)


def load_bookings():
    return _load_json_list(BOOKINGS_PATH)


def save_bookings(items):
    with _BOOKINGS_LOCK:
        _save_json_list(BOOKINGS_PATH, items)


# ===== Telegram-уведомление =====
def notify_admin(text):
    """Шлёт админу сообщение через Telegram Bot API. Возвращает True/False."""
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        print("⚠ BOT_TOKEN или ADMIN_CHAT_ID не задан — уведомление не отправлено.", flush=True)
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": ADMIN_CHAT_ID, "text": text},
            timeout=10,
        )
        if r.ok:
            return True
        print(f"⚠ Telegram API error: {r.status_code} {r.text}", flush=True)
        return False
    except Exception as e:
        print(f"⚠ notify_admin exception: {e}", flush=True)
        return False


# ===== Endpoints =====
@app.route("/", methods=["GET"])
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/api", methods=["GET"])
def api_info():
    return jsonify({
        "name": "TelegramBot Booking API",
        "endpoints": {
            "GET /slots": "вернуть свободные слоты",
            "POST /booking": "создать запись (name, phone, service, date, time)",
        },
    })


@app.route("/slots", methods=["GET"])
def get_slots():
    """Возвращает только свободные слоты."""
    slots = load_slots()
    free = [s for s in slots if s.get("status") == "free"]
    return jsonify(free)


@app.route("/booking", methods=["POST"])
def post_booking():
    """Принимает JSON: {name, phone, service, date, time}.
    Проверяет что слот свободен → бронирует → уведомляет админа."""
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    service = (data.get("service") or "").strip()
    date = (data.get("date") or "").strip()
    time = (data.get("time") or "").strip()

    # Валидация полей
    missing = [k for k, v in (
        ("name", name), ("phone", phone), ("service", service),
        ("date", date), ("time", time),
    ) if not v]
    if missing:
        return jsonify({
            "ok": False,
            "error": f"Обязательные поля пустые: {', '.join(missing)}",
        }), 400

    if not _is_valid_phone(phone):
        return jsonify({"ok": False, "error": "Неверный формат телефона"}), 400

    # Debug: что получили в payload
    print(f"[booking] payload: {data}", flush=True)
    print(f"[booking] normalized request: date={_norm(date)!r} time={_norm(time)!r} service={_norm(service)!r}", flush=True)

    # Поиск свободного слота с нормализацией строк
    slots = load_slots()
    print(f"[booking] loaded {len(slots)} slot(s)", flush=True)
    n_date = _norm(date)
    n_time = _norm(time)
    n_service = _norm(service)
    target = None
    for i, s in enumerate(slots):
        s_date = _norm(s.get("date"))
        s_time = _norm(s.get("time"))
        s_service = _norm(s.get("service"))
        s_status = _norm(s.get("status"))
        match = (s_date == n_date and s_time == n_time
                 and s_service == n_service and s_status == "free")
        print(
            f"[booking] slot[{i}] date={s_date!r} time={s_time!r} "
            f"service={s_service!r} status={s_status!r} → match={match}",
            flush=True,
        )
        if match:
            target = s
            break
    if not target:
        print("[booking] result: no matching free slot → 409", flush=True)
        return jsonify({
            "ok": False,
            "error": "Слот не найден или уже занят",
        }), 409

    # 1) Бронируем слот
    target["status"] = "booked"
    save_slots(slots)

    # 2) Сохраняем запись (используем значения из слота, чтобы не зависеть от регистра ввода)
    bookings = load_bookings()
    new_booking = {
        "client_name": name,
        "service": target.get("service", service),
        "date": target.get("date", date),
        "time": target.get("time", time),
        "phone": phone,
        "client_chat_id": None,        # запись с сайта — нет Telegram chat_id
        "client_reminder_sent": False,
        "source": "web",
    }
    bookings.append(new_booking)
    save_bookings(bookings)

    # 3) Уведомляем админа
    admin_msg = (
        "📅 Новая запись (с сайта):\n"
        f"Клиент: {name}\n"
        f"Телефон: {phone}\n"
        f"Услуга: {service}\n"
        f"Дата: {date}\n"
        f"Время: {time}"
    )
    notified = notify_admin(admin_msg)
    print(f"[booking] saved + admin notified: {notified}", flush=True)

    return jsonify({
        "ok": True,
        "booking": {
            "name": name,
            "phone": phone,
            "service": service,
            "date": date,
            "time": time,
        },
        "admin_notified": notified,
    }), 201


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50, flush=True)
    print("API STARTING", flush=True)
    print(f"TOKEN EXISTS: {bool(BOT_TOKEN)}", flush=True)
    print(f"ADMIN_CHAT_ID EXISTS: {bool(ADMIN_CHAT_ID)}", flush=True)
    print(f"Listening on http://0.0.0.0:{port}", flush=True)
    print("=" * 50, flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
