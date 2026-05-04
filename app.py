import os
from uuid import uuid4
import psycopg2
from psycopg2 import Error as PsycopgError
from psycopg2 import OperationalError
from psycopg2.extras import RealDictCursor
from psycopg2 import sql
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
        port=DB_PORT,
        connect_timeout=5,
        sslmode="require"
    )


def database_error_response(message, error):
    if error is None:
        app.logger.error(message)
    else:
        app.logger.exception(message, exc_info=error)
    return jsonify({"error": message}), 503


def get_landmark_coordinate_columns(cur):
    columns = get_table_columns(cur, "landmark")

    candidates = [
        ("latitude", "longitude"),
        ("lat", "lng"),
        ("lat", "lon"),
        ("latitude", "lng"),
        ("latitude", "lon"),
    ]

    for latitude_column, longitude_column in candidates:
        if latitude_column in columns and longitude_column in columns:
            return latitude_column, longitude_column

    return None, None


def get_table_columns(cur, table_name):
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s;
        """,
        (table_name,)
    )
    return {row["column_name"] for row in cur.fetchall()}


def get_first_matching_column(columns, candidates):
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None

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
# API: Cities
# --------------------------------------------------

@app.route("/api/cities")
def get_cities():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
    except OperationalError:
        return database_error_response(
            "Database connection failed. Check the Supabase Postgres host and credentials.",
            error=None
        )
    except PsycopgError as error:
        return database_error_response("Database query failed while loading cities.", error)

    try:
        cur.execute(
            """
            SELECT id, name
            FROM city
            ORDER BY name;
            """
        )
        cities = cur.fetchall()
    except PsycopgError as error:
        conn.rollback()
        return database_error_response("Database query failed while loading cities.", error)
    finally:
        cur.close()
        conn.close()

    return jsonify({
        "cities": [
            {"id": city["id"], "name": city["name"]}
            for city in cities
        ]
    })

# --------------------------------------------------
# API: Start Game
# --------------------------------------------------

@app.route("/api/start", methods=["POST"])
def start_game():
    data = request.get_json() or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    city_id = data.get("city_id")

    if not name or not email or not city_id:
        return jsonify({"error": "Name, email, and city are required"}), 400

    session_id = str(uuid4())

    try:
        conn = get_db()
        cur = conn.cursor()
    except OperationalError:
        return database_error_response(
            "Database connection failed. Check the Supabase Postgres host and credentials.",
            error=None
        )

    try:
        cur.execute(
            """
            SELECT id
            FROM city
            WHERE id = %s;
            """,
            (city_id,)
        )
        city = cur.fetchone()

        if not city:
            return jsonify({"error": "Selected city does not exist."}), 400

        cur.execute(
            """
            INSERT INTO session (session_id, name, email, city_id, current_landmark, score, completed)
            VALUES (%s, %s, %s, %s, 1, 0, FALSE);
            """,
            (session_id, name, email, city_id)
        )

        conn.commit()
    except PsycopgError as error:
        conn.rollback()
        return database_error_response("Database write failed while starting the game.", error)
    finally:
        cur.close()
        conn.close()

    return jsonify({"session_id": session_id}), 201

# --------------------------------------------------
# API: Get Current Question
# --------------------------------------------------

@app.route("/api/question/<session_id>")
def get_current_question(session_id):
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
    except OperationalError:
        return database_error_response(
            "Database connection failed. Check the Supabase Postgres host and credentials.",
            error=None
        )

    try:
        latitude_column, longitude_column = get_landmark_coordinate_columns(cur)
        landmark_columns = get_table_columns(cur, "landmark")
        riddle_column = get_first_matching_column(landmark_columns, ["riddle", "clue"])
        hint_column = get_first_matching_column(landmark_columns, ["hint", "riddle_hint", "clue_hint"])

        if latitude_column and longitude_column:
            query = sql.SQL(
                """
                SELECT
                    q.question_number,
                    q.question,
                    q.a,
                    q.b,
                    q.c,
                    q.d,
                    l.name AS landmark_name,
                    l.{latitude_column} AS latitude,
                    l.{longitude_column} AS longitude,
                    {riddle_select} AS riddle,
                    {hint_select} AS hint
                FROM session s
                JOIN city c ON c.id = s.city_id
                JOIN landmark l ON l.city_id = c.id
                JOIN question q ON q.landmark_id = l.id
                WHERE s.session_id = %s
                  AND q.question_number = s.current_landmark;
                """
            ).format(
                latitude_column=sql.Identifier(latitude_column),
                longitude_column=sql.Identifier(longitude_column),
                riddle_select=sql.Identifier("l", riddle_column) if riddle_column else sql.SQL("NULL"),
                hint_select=sql.Identifier("l", hint_column) if hint_column else sql.SQL("NULL"),
            )
        else:
            query = sql.SQL(
                """
                SELECT
                    q.question_number,
                    q.question,
                    q.a,
                    q.b,
                    q.c,
                    q.d,
                    l.name AS landmark_name,
                    NULL::double precision AS latitude,
                    NULL::double precision AS longitude,
                    {riddle_select} AS riddle,
                    {hint_select} AS hint
                FROM session s
                JOIN city c ON c.id = s.city_id
                JOIN landmark l ON l.city_id = c.id
                JOIN question q ON q.landmark_id = l.id
                WHERE s.session_id = %s
                  AND q.question_number = s.current_landmark;
                """
            ).format(
                riddle_select=sql.Identifier("l", riddle_column) if riddle_column else sql.SQL("NULL"),
                hint_select=sql.Identifier("l", hint_column) if hint_column else sql.SQL("NULL"),
            )

        cur.execute(query, (session_id,))
        question = cur.fetchone()
    except PsycopgError as error:
        conn.rollback()
        return database_error_response("Database query failed while loading the question.", error)
    finally:
        cur.close()
        conn.close()

    if not question:
        return jsonify({"error": "Question not found"}), 404

    return jsonify({
        "number": question["question_number"],
        "total": 15,
        "landmark_name": question["landmark_name"],
        "latitude": question["latitude"],
        "longitude": question["longitude"],
        "riddle": question["riddle"],
        "hint": question["hint"],
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

    data = request.get_json() or {}
    user_answer = data.get("answer")

    if not user_answer:
        return jsonify({"error": "Answer required"}), 400

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
    except OperationalError:
        return database_error_response(
            "Database connection failed. Check the Supabase Postgres host and credentials.",
            error=None
        )

    try:
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

        if not row:
            return jsonify({"error": "Session or question not found"}), 404

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
    except PsycopgError as error:
        conn.rollback()
        return database_error_response("Database operation failed while saving the answer.", error)
    finally:
        cur.close()
        conn.close()

    return jsonify({
        "correct": is_correct,
        "correct_answer": correct_answer,
        "next": "completed" if completed else "next",
        "next_step": "completed" if completed else "next_question"
    })

# --------------------------------------------------
# Render Port Binding
# --------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
