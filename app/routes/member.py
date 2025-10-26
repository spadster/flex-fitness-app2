from flask import Blueprint, render_template, session, flash, redirect, request, url_for, jsonify
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
# Dashboard + Add Food
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
    # Handle search submission
    # -----------------------------
    search_results = []
    if request.method == "POST":
        search_query = request.form.get("food_search", "").strip()
        quantity_input = request.form.get("log_quantity", "").strip()
        food_id = request.form.get("food_id")

        # If user is trying to add a food log
        if food_id and quantity_input:
            try:
                quantity = float(quantity_input)
                if quantity <= 0:
                    raise ValueError
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
                flash("Please enter a valid quantity in grams.", "danger")
            return redirect(url_for("member.dashboard"))

        # If user just typed something but didn't select a suggestion
        elif search_query:
            search_results = Food.query.filter(Food.name.ilike(f"%{search_query}%")).limit(10).all()
            if not search_results:
                flash("No matching foods found.", "warning")
        else:
            flash("Please enter a food name to search.", "warning")

    # -----------------------------
    # Fetch today's logs + totals
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

@member_bp.route("/search-foods")
def search_foods():
    query = request.args.get("q", "").strip()
    results = []
    if query:
        foods = Food.query.filter(Food.name.ilike(f"%{query}%")).limit(10).all()
        for food in foods:
            results.append({
                "id": food.id,
                "name": food.name,
                "calories": food.calories,
                "protein": food.protein_g,
                "carbs": food.carbs_g,
                "fats": food.fats_g
            })
    return jsonify({"results": results})


# -----------------------------
# View Progress
# -----------------------------
@member_bp.route('/progress')
def view_progress():
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id or role != 'member':
        return "Access denied", 403

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

    trainer_code = request.form.get("trainer_code", "").upper().strip()
    trainer = User.query.filter_by(trainer_code=trainer_code, role='trainer').first()
    if not trainer:
        flash("Invalid trainer code.", "danger")
        return redirect(request.referrer or url_for("member.dashboard"))

    member = User.query.get(member_id)
    member.trainer_id = trainer.id
    db.session.commit()
    flash(f"You are now registered with trainer {trainer.first_name} {trainer.last_name}.", "success")
    return redirect(request.referrer or url_for("member.dashboard"))

# -----------------------------
# Exercise Plan
# -----------------------------
@member_bp.route('/exercise-plan')
def exercise_plan():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login_member"))

    user = User.query.get(user_id)
    # Dummy plan for now — replace with real query if needed
    plan = []
    return render_template("exercise-plan.html", user=user, plan=plan)

@member_bp.route('/add-custom-food', methods=['POST'])
def add_custom_food():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in first.", "danger")
        return redirect(url_for("auth.login_member"))

    name = request.form.get("custom_name").strip()
    calories = float(request.form.get("calories") or 0)
    protein_g = float(request.form.get("protein_g") or 0)
    carbs_g = float(request.form.get("carbs_g") or 0)
    fats_g = float(request.form.get("fats_g") or 0)

    if not name:
        flash("Food name cannot be empty.", "danger")
        return redirect(url_for("member.dashboard"))

    food = Food(
        name=name,
        source_id=None,  # custom foods don't have a USDA ID
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fats_g=fats_g
    )
    db.session.add(food)
    db.session.commit()
    flash(f"Custom food '{name}' added!", "success")
    return redirect(url_for("member.dashboard"))
