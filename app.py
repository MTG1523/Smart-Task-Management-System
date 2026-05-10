from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from config import Config
import pandas as pd
import numpy as np

app = Flask(__name__)
app.config.from_object(Config)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
socketio = SocketIO(app, cors_allowed_origins="*")

login_manager.login_view = "login"
login_manager.login_message_category = "info"


# ── Models ────────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id           = db.Column(db.Integer, primary_key=True)
    username     = db.Column(db.String(80), unique=True, nullable=False)
    email        = db.Column(db.String(120), unique=True, nullable=False)
    password_hash= db.Column(db.String(256), nullable=False)
    created_at   = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    tasks        = db.relationship("Task", backref="owner", lazy=True, cascade="all, delete-orphan")

    def set_password(self, p): self.password_hash = generate_password_hash(p)
    def check_password(self, p): return check_password_hash(self.password_hash, p)
    def to_dict(self):
        return {"id": self.id, "username": self.username, "email": self.email}


class Task(db.Model):
    __tablename__ = "tasks"
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    priority    = db.Column(db.String(20), nullable=False, default="medium")
    status      = db.Column(db.String(20), nullable=False, default="pending")
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                            onupdate=lambda: datetime.now(timezone.utc))
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    def to_dict(self):
        return {
            "id": self.id, "title": self.title, "description": self.description,
            "priority": self.priority, "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "user_id": self.user_id,
        }


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ── Auth routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("dashboard") if current_user.is_authenticated else url_for("login"))

@app.route("/auth/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form
        username = data.get("username", "").strip()
        email    = data.get("email", "").strip().lower()
        password = data.get("password", "")
        if not username or not email or not password:
            flash("All fields are required.", "danger")
            return render_template("register.html")
        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "danger")
            return render_template("register.html")
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "danger")
            return render_template("register.html")
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/auth/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        data     = request.get_json() if request.is_json else request.form
        email    = data.get("email", "").strip().lower()
        password = data.get("password", "")
        remember = data.get("remember", False)
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html")
        login_user(user, remember=bool(remember))
        return redirect(url_for("dashboard"))
    return render_template("login.html")

@app.route("/auth/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)


# ── Task API ──────────────────────────────────────────────────────────────────

@app.route("/api/tasks", methods=["GET"])
@login_required
def get_tasks():
    status   = request.args.get("status")
    priority = request.args.get("priority")
    q = Task.query.filter_by(user_id=current_user.id)
    if status:   q = q.filter_by(status=status)
    if priority: q = q.filter_by(priority=priority)
    tasks = q.order_by(Task.created_at.desc()).all()
    return jsonify({"tasks": [t.to_dict() for t in tasks], "count": len(tasks)}), 200

@app.route("/api/tasks", methods=["POST"])
@login_required
def add_task():
    data = request.get_json()
    if not data: return jsonify({"error": "JSON required"}), 400
    title = data.get("title", "").strip()
    if not title: return jsonify({"error": "Title required"}), 400
    priority = data.get("priority", "medium")
    status   = data.get("status", "pending")
    if priority not in ("low","medium","high"):
        return jsonify({"error": "Invalid priority"}), 400
    if status not in ("pending","in_progress","completed"):
        return jsonify({"error": "Invalid status"}), 400
    task = Task(title=title, description=data.get("description",""),
                priority=priority, status=status, user_id=current_user.id)
    db.session.add(task)
    db.session.commit()
    socketio.emit("task_created", task.to_dict(), room=f"user_{current_user.id}")
    return jsonify({"message": "Task created", "task": task.to_dict()}), 201

@app.route("/api/tasks/<int:task_id>", methods=["GET"])
@login_required
def get_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    return jsonify({"task": task.to_dict()}), 200

@app.route("/api/tasks/<int:task_id>", methods=["PUT"])
@login_required
def update_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    if not data: return jsonify({"error": "JSON required"}), 400
    if "title"       in data: task.title       = data["title"].strip() or task.title
    if "description" in data: task.description = data["description"]
    if "priority"    in data:
        if data["priority"] not in ("low","medium","high"):
            return jsonify({"error": "Invalid priority"}), 400
        task.priority = data["priority"]
    if "status" in data:
        if data["status"] not in ("pending","in_progress","completed"):
            return jsonify({"error": "Invalid status"}), 400
        task.status = data["status"]
    task.updated_at = datetime.now(timezone.utc)
    db.session.commit()
    socketio.emit("task_updated", task.to_dict(), room=f"user_{current_user.id}")
    return jsonify({"message": "Task updated", "task": task.to_dict()}), 200

@app.route("/api/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    db.session.delete(task)
    db.session.commit()
    socketio.emit("task_deleted", {"id": task_id}, room=f"user_{current_user.id}")
    return jsonify({"message": "Task deleted"}), 200


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.route("/analytics/summary", methods=["GET"])
@login_required
def analytics_summary():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    if not tasks:
        return jsonify({"total_tasks":0,"completed_tasks":0,"pending_tasks":0,
                        "in_progress_tasks":0,"completion_percentage":0.0,
                        "priority_breakdown":{"low":0,"medium":0,"high":0}}), 200
    df = pd.DataFrame([t.to_dict() for t in tasks])
    total       = int(len(df))
    completed   = int((df["status"] == "completed").sum())
    pending     = int((df["status"] == "pending").sum())
    in_progress = int((df["status"] == "in_progress").sum())
    pct         = float(np.round((completed / total) * 100, 2)) if total else 0.0
    pc = df["priority"].value_counts().to_dict()
    return jsonify({
        "total_tasks": total, "completed_tasks": completed,
        "pending_tasks": pending, "in_progress_tasks": in_progress,
        "completion_percentage": pct,
        "priority_breakdown": {
            "low": int(pc.get("low",0)),
            "medium": int(pc.get("medium",0)),
            "high": int(pc.get("high",0)),
        },
    }), 200


# ── WebSocket ─────────────────────────────────────────────────────────────────

@socketio.on("join")
def on_join(data):
    user_id = data.get("user_id")
    if user_id:
        join_room(f"user_{user_id}")
        emit("status", {"message": "connected"})


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    socketio.run(app, debug=True, host="0.0.0.0", port=5000)
