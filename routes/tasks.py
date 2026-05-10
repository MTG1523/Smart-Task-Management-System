from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_login import login_required, current_user
from app import db, socketio
from models.models import Task
from flask_socketio import emit

tasks_bp = Blueprint("tasks", __name__)


# ── Dashboard (HTML) ────────────────────────────────────────────────────────

@tasks_bp.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", user=current_user)


# ── REST API ─────────────────────────────────────────────────────────────────

@tasks_bp.route("/tasks", methods=["GET"])
@login_required
def get_tasks():
    """Get all tasks for the current user with optional filters."""
    status = request.args.get("status")
    priority = request.args.get("priority")

    query = Task.query.filter_by(user_id=current_user.id)
    if status:
        query = query.filter_by(status=status)
    if priority:
        query = query.filter_by(priority=priority)

    tasks = query.order_by(Task.created_at.desc()).all()
    return jsonify({"tasks": [t.to_dict() for t in tasks], "count": len(tasks)}), 200


@tasks_bp.route("/tasks", methods=["POST"])
@login_required
def add_task():
    """Create a new task."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required."}), 400

    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "Title is required."}), 400

    priority = data.get("priority", "medium")
    if priority not in ("low", "medium", "high"):
        return jsonify({"error": "Priority must be low, medium, or high."}), 400

    status = data.get("status", "pending")
    if status not in ("pending", "in_progress", "completed"):
        return jsonify({"error": "Status must be pending, in_progress, or completed."}), 400

    task = Task(
        title=title,
        description=data.get("description", ""),
        priority=priority,
        status=status,
        user_id=current_user.id,
    )
    db.session.add(task)
    db.session.commit()

    # Broadcast via WebSocket
    socketio.emit("task_created", task.to_dict(), room=f"user_{current_user.id}")

    return jsonify({"message": "Task created.", "task": task.to_dict()}), 201


@tasks_bp.route("/tasks/<int:task_id>", methods=["GET"])
@login_required
def get_task(task_id):
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    return jsonify({"task": task.to_dict()}), 200


@tasks_bp.route("/tasks/<int:task_id>", methods=["PUT"])
@login_required
def update_task(task_id):
    """Update an existing task."""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required."}), 400

    if "title" in data:
        task.title = data["title"].strip() or task.title
    if "description" in data:
        task.description = data["description"]
    if "priority" in data:
        if data["priority"] not in ("low", "medium", "high"):
            return jsonify({"error": "Invalid priority."}), 400
        task.priority = data["priority"]
    if "status" in data:
        if data["status"] not in ("pending", "in_progress", "completed"):
            return jsonify({"error": "Invalid status."}), 400
        task.status = data["status"]

    db.session.commit()

    # Broadcast via WebSocket
    socketio.emit("task_updated", task.to_dict(), room=f"user_{current_user.id}")

    return jsonify({"message": "Task updated.", "task": task.to_dict()}), 200


@tasks_bp.route("/tasks/<int:task_id>", methods=["DELETE"])
@login_required
def delete_task(task_id):
    """Delete a task."""
    task = Task.query.filter_by(id=task_id, user_id=current_user.id).first_or_404()
    task_data = task.to_dict()
    db.session.delete(task)
    db.session.commit()

    # Broadcast via WebSocket
    socketio.emit("task_deleted", {"id": task_id}, room=f"user_{current_user.id}")

    return jsonify({"message": "Task deleted.", "task": task_data}), 200


# ── WebSocket events ──────────────────────────────────────────────────────────

@socketio.on("join")
def on_join(data):
    from flask_socketio import join_room
    user_id = data.get("user_id")
    if user_id:
        join_room(f"user_{user_id}")
        emit("status", {"message": f"Joined room user_{user_id}"})
