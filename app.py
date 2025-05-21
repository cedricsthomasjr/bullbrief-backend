# backend/main.py
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from routes import register_routes
import os

load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": [
    "https://bullbrief-frontend.vercel.app",
    "http://localhost:3000", "https://www.bullbrief.pro"
]}})


# Register all app routes (e.g., /summary, /eps, etc.)
register_routes(app)

# Root route for Render healthcheck
@app.route("/")
def home():
    return jsonify({"status": "BullBrief API is live"})

# Render-compatible server start
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
