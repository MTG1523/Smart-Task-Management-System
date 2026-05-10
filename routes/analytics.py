from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from models.models import Task
import pandas as pd
import numpy as np

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/summary", methods=["GET"])
@login_required
def summary():
    """
    Returns task analytics for the current user using Pandas & NumPy.
    """
    tasks = Task.query.filter_by(user_id=current_user.id).all()

    if not tasks:
        return jsonify({
            "total_tasks": 0,
            "completed_tasks": 0,
            "pending_tasks": 0,
            "in_progress_tasks": 0,
            "completion_percentage": 0.0,
            "priority_breakdown": {"low": 0, "medium": 0, "high": 0},
            "avg_tasks_per_priority": 0.0,
            "status_distribution": [],
        }), 200

    # Build DataFrame
    df = pd.DataFrame([t.to_dict() for t in tasks])

    # Core counts
    total = int(len(df))
    completed = int((df["status"] == "completed").sum())
    pending = int((df["status"] == "pending").sum())
    in_progress = int((df["status"] == "in_progress").sum())

    # Completion % via NumPy
    completion_pct = float(np.round((completed / total) * 100, 2)) if total > 0 else 0.0

    # Priority breakdown
    priority_counts = df["priority"].value_counts().to_dict()
    priority_breakdown = {
        "low": int(priority_counts.get("low", 0)),
        "medium": int(priority_counts.get("medium", 0)),
        "high": int(priority_counts.get("high", 0)),
    }

    # Average tasks per priority level using NumPy
    avg_tasks_per_priority = float(np.mean(list(priority_breakdown.values())))

    # Status distribution for chart
    status_distribution = (
        df.groupby("status")
        .size()
        .reset_index(name="count")
        .to_dict(orient="records")
    )

    # Recent activity — last 7 days
    df["created_at"] = pd.to_datetime(df["created_at"])
    recent = df[df["created_at"] >= pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)]
    recent_count = int(len(recent))

    return jsonify({
        "total_tasks": total,
        "completed_tasks": completed,
        "pending_tasks": pending,
        "in_progress_tasks": in_progress,
        "completion_percentage": completion_pct,
        "priority_breakdown": priority_breakdown,
        "avg_tasks_per_priority": round(avg_tasks_per_priority, 2),
        "status_distribution": status_distribution,
        "recent_tasks_7d": recent_count,
    }), 200
