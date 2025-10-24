from flask import Blueprint, render_template, session, flash, redirect, request, url_for
from app import db
from app.models import User, Progress, Food, UserFoodLog
from datetime import datetime

member_bp = Blueprint('member', __name__, url_prefix='/member')


# -----------------------------
# Context processor to inject user
# -----------------------------
@member_bp.app_context_processor
def inject_user():
    user_id = session.get("user_id")
    if user_id:
        return {"user": User.query.get(user_id)}
    return {}


# -----------------------------
# Member Dashboard (Food Logs + Macros)
# -----------------------------
@member_bp.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    user_id = session.get("user_id")
    role = session.get("role")
    if not user_id or role != 'member':
        flash("Please log in as a member.", "danger")
        return redirect(url_for("auth.login_member"))

    user = User.query.get(user_id)
    today = datetime.utcnow().date()

    # -----------------------------
    # Handle food search & add
    # -----------------------------
    search_results = []
    if request.method == "POST":
        search_query = request.form.get("food_search", "").strip()
        quantity_input = request.form.get("quantity", "0").strip()

        # Validate quantity
        try:
            quantity = float(quantity_input)
        except ValueError:
            quantity = 0

        if quantity <= 0:
            flash("Please enter a valid quantity in grams.", "danger")
        elif search_query:
            # Search foods (case-insensitive)
            search_results = Food.query.filter(Food.name.ilike(f"%{search_query}%")).limit(10).all()
            if not search_results:
                flash("No matching foods found.", "warning")
        else:
            flash("Please enter a food name to search.", "warning")

    # -----------------------------
    # Handle adding a specific food log
    # -----------------------------
    food_id = request.form.get("food_id")
    quantity = request.form.get("log_quantity")
    if food_id and quantity:
        try:
            quantity = float(quantity)
            food = Food.query.get(int(food_id))
            if food:
                log = UserFoodLog(
                    user_id=user.id,
                    food_id=food.id,
                    quantity=quantity,
                    log_date=today
                )
                db.session.add(log)
                db.session.commit()
                flash(f"Added {quantity}g of {food.name} to your tracker!", "success")
            else:
                flash("Selected food not found.", "danger")
        except ValueError:
            flash("Invalid quantity.", "danger")
        return redirect(url_for("member.dashboard"))

    # -----------------------------
    # Fetch today's food logs and calculate totals
    # -----------------------------
    user_food_logs = UserFoodLog.query.filter_by(user_id=user.id, log_date=today).all()

    totals = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
    for log in user_food_logs:
        factor = log.quantity / 100
        totals["calories"] += (log.food.calories or 0) * factor
        totals["protein"] += (log.food.protein_g or 0) * factor
        totals["carbs"] += (log.food.carbs_g or 0) * factor
        totals["fat"] += (log.food.fats_g or 0) * factor

    return render_template(
        "dashboard-member.html",
        user=user,
        user_food_logs=user_food_logs,
        totals=totals,
        search_results=search_results
    )


# -----------------------------
# View Member Progress
# -----------------------------
@member_bp.route('/progress')
def view_progress():
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id or role != 'member':
        return "Access denied", 403

    member = User.query.get(user_id)
    progress_entries = Progress.query.filter_by(user_id=user_id).order_by(Progress.date.desc()).all()
    return render_template('display-member.html', progress_entries=progress_entries)


# -----------------------------
# Register Member with Trainer
# -----------------------------
@member_bp.route('/register-trainer', methods=['POST'])
def register_trainer():
    member_id = session.get('user_id')
    if not member_id:
        return "Please log in first", 403

    member = User.query.get(member_id)
    trainer_code = request.form.get("trainer_code", "").upper().strip()

    trainer = User.query.filter_by(trainer_code=trainer_code, role='trainer').first()
    if not trainer:
        flash("Invalid trainer code.", "danger")
        return redirect(request.referrer or url_for("member.dashboard"))

    member.trainer_id = trainer.id
    db.session.commit()
    flash(f"You are now registered with trainer {trainer.first_name} {trainer.last_name}.", "success")
    return redirect(request.referrer or url_for("member.dashboard"))

@member_bp.route('/exercise-plan')
def exercise_plan():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login_member"))

    user = User.query.get(user_id)
    # Fetch exercise plan from DB or return dummy data
    plan = []  # replace with actual query
    return render_template("exercise-plan.html", user=user, plan=plan)
