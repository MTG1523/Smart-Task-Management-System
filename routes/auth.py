from flask import Blueprint, request, jsonify, render_template, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from app import db
from models.models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("tasks.dashboard"))

    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form

        username = data.get("username", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not username or not email or not password:
            msg = "All fields are required."
            if request.is_json:
                return jsonify({"error": msg}), 400
            flash(msg, "danger")
            return render_template("register.html")

        if User.query.filter_by(username=username).first():
            msg = "Username already taken."
            if request.is_json:
                return jsonify({"error": msg}), 409
            flash(msg, "danger")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            msg = "Email already registered."
            if request.is_json:
                return jsonify({"error": msg}), 409
            flash(msg, "danger")
            return render_template("register.html")

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        if request.is_json:
            return jsonify({"message": "User registered successfully.", "user": user.to_dict()}), 201

        flash("Account created! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("tasks.dashboard"))

    if request.method == "POST":
        data = request.get_json() if request.is_json else request.form

        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        remember = data.get("remember", False)

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            msg = "Invalid email or password."
            if request.is_json:
                return jsonify({"error": msg}), 401
            flash(msg, "danger")
            return render_template("login.html")

        login_user(user, remember=bool(remember))

        if request.is_json:
            return jsonify({"message": "Login successful.", "user": user.to_dict()}), 200

        return redirect(url_for("tasks.dashboard"))

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
