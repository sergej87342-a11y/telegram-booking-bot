import os
import json
from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# ====== ФАЙЛЫ ======
SLOTS_FILE = "slots.json"
BOOKINGS_FILE = "bookings.json"

# ====== ГЛАВНАЯ СТРАНИЦА ======
@app.route("/")
def home():
    return send_from_directory(".", "index.html")

# ====== API ======

@app.route("/slots", methods=["GET"])
def get_slots():
    try:
        with open(SLOTS_FILE, "r", encoding="utf-8") as f:
            slots = json.load(f)
        return jsonify(slots)
    except:
        return jsonify([])

@app.route("/booking", methods=["POST"])
def create_booking():
    data = request.json

    booking = {
        "name": data.get("name"),
        "phone": data.get("phone"),
        "service": data.get("service"),
        "date": data.get("date"),
        "time": data.get("time")
    }

    try:
        with open(BOOKINGS_FILE, "r", encoding="utf-8") as f:
            bookings = json.load(f)
    except:
        bookings = []

    bookings.append(booking)

    with open(BOOKINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(bookings, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "ok"})

# ====== ЗАПУСК ======
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)