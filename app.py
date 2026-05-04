import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, jsonify, request, render_template
from dotenv import load_dotenv
import requests

# --------------------------------------------------
# Setup
# --------------------------------------------------

load_dotenv()
app = Flask(__name__, template_folder="templates")

DB_HOST = os.environ.get("SUPABASE_DB_HOST")
DB_NAME = os.environ.get("SUPABASE_DB_NAME")
DB_USER = os.environ.get("SUPABASE_DB_USER")
DB_PASSWORD = os.environ.get("SUPABASE_DB_PASSWORD")
DB_PORT = os.environ.get("SUPABASE_DB_PORT", "5432")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

# --------------------------------------------------
# Database Helper
# --------------------------------------------------

def get_db():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )

# --------------------------------------------------
# Email Helper
# --------------------------------------------------

def send_results_email(name, email, city, score):
    requests.post(
        f"{SUPABASE_URL}/functions/v1/send-results-email",
        headers={
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": "application/json"
        },
        json={
            "name": name,
            "email": email,
            "city": city,
            "score": f"{score}/15"
        }
    )

# --------------------------------------------------
# ✅ NEW: Home Page Route
# --------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")

# --------------------------------------------------
# API: Health
# --------------------------------------------------

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

# --------------------------------------------------
# API: Get Current Question
# --------------------------------------------------

@app.route("/api/question/<session_id>")
def get_current_question(session_id):

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    sql = """
    SELECT
        q.question_number,
        q.question,
        q.a,
        q.b,
        q.c,
        q.d
    FROM session s
    JOIN city c ON c.id = s.city_id
    JOIN landmark l ON l.city_id = c.id
    JOIN question q ON q.landmark_id = l.id
    WHERE s.session_id = %s
      AND q.question_number = s.current_landmark;
    """

    cur.execute(sql, (session_id,))
    question = cur.fetchone()

    cur.close()
    conn.close()

    if not question:
        return jsonify({"error": "Question not found"}), 404

    return jsonify({
        "number": question["question_number"],
        "total": 15,
        "question": question["question"],
        "options": [
            question["a"],
            question["b"],
            question["c"],
            question["d"]
        ]
    })

# --------------------------------------------------
# API: Submit Answer
# --------------------------------------------------

@app.route("/api/answer/<session_id>", methods=["POST"])
def submit_answer(session_id):

    data = request.get_json()
    user_answer = data.get("answer")

    if not user_answer:
        return jsonify({"error": "Answer required"}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    sql = """
    SELECT
        q.correct,
        s.current_landmark,
        s.score,
        s.name,
        s.email,
        c.name AS city_name
    FROM session s
    JOIN city c ON c.id = s.city_id
    JOIN landmark l ON l.city_id = c.id
    JOIN question q ON q.landmark_id = l.id
    WHERE s.session_id = %s
      AND q.question_number = s.current_landmark;
    """

    cur.execute(sql, (session_id,))
    row = cur.fetchone()

    correct_answer = row["correct"]
    current_number = row["current_landmark"]
    current_score = row["score"]
    name = row["name"]
    email = row["email"]
    city_name = row["city_name"]

    is_correct = (user_answer == correct_answer)
    if is_correct:
        current_score += 1

    if current_number < 15:
        cur.execute(
            "UPDATE session SET current_landmark = current_landmark + 1, score = %s WHERE session_id = %s;",
            (current_score, session_id)
        )
        completed = False
    else:
        cur.execute(
            "UPDATE session SET completed = TRUE, score = %s WHERE session_id = %s;",
            (current_score, session_id)
        )
        completed = True
        send_results_email(name, email, city_name, current_score)

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "correct": is_correct,
        "next": "completed" if completed else "next"
    })

# --------------------------------------------------
# Render Port Binding
# --------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)