from flask import Flask, jsonify, request, send_from_directory
import json
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -----------------------------
# ГЛАВНАЯ СТРАНИЦА (САЙТ)
# -----------------------------
@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


# -----------------------------
# API
# -----------------------------
@app.route("/slots", methods=["GET"])
def get_slots():
    try:
        with open(os.path.join(BASE_DIR, "slots.json"), "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
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
        with open(os.path.join(BASE_DIR, "bookings.json"), "r", encoding="utf-8") as f:
            bookings = json.load(f)
    except:
        bookings = []

    bookings.append(booking)

    with open(os.path.join(BASE_DIR, "bookings.json"), "w", encoding="utf-8") as f:
        json.dump(bookings, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "ok"})


# -----------------------------
# ЗАПУСК
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)