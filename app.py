from flask import Flask, jsonify, send_file
import os

app = Flask(__name__)

@app.route("/")
def index():
    return send_file("index.html")

@app.route("/slots")
def slots():
    return jsonify({"slots": []})

@app.route("/booking", methods=["POST"])
def booking():
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("STARTING APP ON PORT:", port)
    app.run(host="0.0.0.0", port=port)