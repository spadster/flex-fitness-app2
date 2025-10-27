from flask import Blueprint, render_template, session, flash, redirect, request, url_for, jsonify
from app import db
from app.models import User, Progress, Food, UserFoodLog, FoodMeasure
from datetime import datetime

member_bp = Blueprint('member', __name__, url_prefix='/member')

# -----------------------------
# Inject user into templates
# -----------------------------
@member_bp.app_context_processor
def inject_user():
    user_id = session.get("user_id")
    if user_id:
        return {"user": User.query.get(user_id)}
    return {}

@member_bp.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    user_id = session.get("user_id")
    role = session.get("role")
    if not user_id or role != 'member':
        flash("Please log in as a member.", "danger")
        return redirect(url_for("auth.login_member"))

    user = User.query.get(user_id)
    today = datetime.utcnow().date()
    search_results = []

    if request.method == "POST":
        search_query = request.form.get("food_search", "").strip()
        quantity_input = request.form.get("log_quantity", "").strip()
        food_id = request.form.get("food_id")
        unit_input = request.form.get("unit", "g").strip().lower()

        # -----------------------------
        # If user just types a name and clicks Add → use top match
        # -----------------------------
        if not food_id and search_query:
            top_result = Food.query.filter(Food.name.ilike(f"%{search_query}%")).first()
            if top_result:
                food_id = top_result.id

        # -----------------------------
        # Add a food log
        # -----------------------------
        if food_id and quantity_input:
            try:
                quantity = float(quantity_input)
                if quantity <= 0:
                    raise ValueError

                food = Food.query.get(int(food_id))
                if not food:
                    flash("Selected food not found.", "danger")
                    return redirect(url_for("member.dashboard"))

                # Check if this food has a specific measure (cup, tbsp, tsp, etc.)
                measure = FoodMeasure.query.filter_by(food_id=food.id, measure_name=unit_input).first()

                if measure:
                    grams = quantity * measure.grams
                elif unit_input in UNIT_TO_GRAMS:
                    grams = quantity * UNIT_TO_GRAMS[unit_input]
                else:
                    grams = quantity  # assume grams by default

                log = UserFoodLog(
                    user_id=user.id,
                    food_id=food.id,
                    quantity=grams,  # store actual grams
                    unit="g",
                    log_date=today
                )
                db.session.add(log)
                db.session.commit()

                flash(f"Added {quantity} {unit_input} of {food.name}!", "success")

            except ValueError:
                flash("Please enter a valid quantity.", "danger")

            return redirect(url_for("member.dashboard"))

        # -----------------------------
        # Search foods without adding
        # -----------------------------
        elif search_query:
            search_results = Food.query.filter(Food.name.ilike(f"%{search_query}%")).limit(10).all()
            if not search_results:
                flash("No matching foods found.", "warning")
        else:
            flash("Please enter a food name to search.", "warning")

    # -----------------------------
    # Fetch today's logs + compute totals
    # -----------------------------
    user_food_logs = UserFoodLog.query.filter_by(user_id=user.id, log_date=today).all()
    totals = {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}

    for log in user_food_logs:
        scaled = log.scaled  # uses your existing @property
        totals["calories"] += scaled["calories"]
        totals["protein"] += scaled["protein"]
        totals["carbs"] += scaled["carbs"]
        totals["fat"] += scaled["fats"]

    return render_template(
        "dashboard-member.html",
        user=user,
        user_food_logs=user_food_logs,
        totals=totals,
        search_results=search_results,
        UNIT_TO_GRAMS=UNIT_TO_GRAMS
    )


UNIT_TO_GRAMS = {
    "g": 1,
    "kg": 1000,
    "oz": 28.35,
    "lb": 453.592,
    "tsp": 4.2,   # approximate
    "tbsp": 14.3,
    "cup": 240
}

def scale_nutrients(food_id, quantity, unit):
    measure = FoodMeasure.query.filter_by(food_id=food_id, measure_name=unit).first()
    if measure:
        grams = quantity * measure.grams
    else:
        # fallback to 100g base if unit is unknown
        grams = quantity

    food = Food.query.get(food_id)
    factor = grams / 100  # assuming macros stored per 100g

    return {
        "calories": round(food.calories * factor, 1),
        "protein_g": round(food.protein_g * factor, 1),
        "carbs": round(food.carbs_g * factor, 1),
        "fats": round(food.fats_g * factor, 1)
    }


# -----------------------------
# Search Foods API
# -----------------------------
@member_bp.route("/search-foods")
def search_foods():
    query = (request.args.get("q") or "").strip()
    unit = request.args.get("unit", "g")
    try:
        quantity = float(request.args.get("quantity", 1))
    except ValueError:
        quantity = 1

    results = []
    if query:
        foods = (
            Food.query
            .filter(Food.name != None)
            .filter(Food.name.ilike(f"%{query}%"))
            .limit(10)
            .all()
        )
        for food in foods:
            # Scale nutrients using food-specific measure if exists
            grams_per_unit = UNIT_TO_GRAMS.get(unit.lower(), 1)
            measure = FoodMeasure.query.filter_by(food_id=food.id, measure_name=unit.lower()).first()
            if measure:
                grams_per_unit = measure.grams

            quantity_in_grams = quantity * grams_per_unit
            serving_grams = food.serving_size or 100
            factor = quantity_in_grams / serving_grams

            results.append({
                "id": food.id,
                "name": food.name,
                "calories": round((food.calories or 0) * factor, 1),
                "protein_g": round((food.protein_g or 0) * factor, 1),
                "carbs": round((food.carbs_g or 0) * factor, 1),
                "fats": round((food.fats_g or 0) * factor, 1),
                "serving_size": food.serving_size,
                "serving_unit": food.serving_unit
            })

    return jsonify({"results": results})

@member_bp.route("/add-food", methods=["POST"])
def add_food():
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in first.", "danger")
        return redirect(url_for("auth.login_member"))

    food_name = request.form.get("food_name", "").strip()
    quantity = float(request.form.get("quantity") or 1)
    unit = request.form.get("unit", "g").strip().lower()  # ← Make sure it's lowercase
    food_id = request.form.get("food_id")
    today = datetime.utcnow().date()

    if food_id:
        # Existing food from DB
        food = Food.query.get(int(food_id))
        if not food:
            flash("Food not found.", "danger")
            return redirect(url_for("member.dashboard"))
    else:
        # New food (custom)
        calories = float(request.form.get("calories") or 0)
        protein_g = float(request.form.get("protein_g") or 0)
        carbs_g = float(request.form.get("carbs_g") or 0)
        fats_g = float(request.form.get("fats_g") or 0)

        food = Food(
            name=food_name,
            calories=calories,
            protein_g=protein_g,
            carbs_g=carbs_g,
            fats_g=fats_g,
            source_id=None,
            serving_size=100,
            serving_unit="g"
        )
        db.session.add(food)
        db.session.commit()

    # ✅ Convert to grams BEFORE saving (same as dashboard route)
    measure = FoodMeasure.query.filter_by(food_id=food.id, measure_name=unit).first()
    
    if measure:
        grams = quantity * measure.grams
    elif unit in UNIT_TO_GRAMS:
        grams = quantity * UNIT_TO_GRAMS[unit]
    else:
        grams = quantity  # assume grams by default

    # Save user log (always in grams)
    log = UserFoodLog(
        user_id=user_id,
        food_id=food.id,
        quantity=grams,  # ← Store as grams
        unit="g",        # ← Always "g"
        log_date=today
    )
    db.session.add(log)
    db.session.commit()

    flash(f"Added {quantity} {unit} of {food.name}!", "success")
    return redirect(url_for("member.dashboard"))

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


@member_bp.route("/get-measures/<int:food_id>")
def get_measures(food_id):
    measures = FoodMeasure.query.filter_by(food_id=food_id).all()
    return jsonify({
        "measures": [{"measure_name": m.measure_name, "grams": m.grams} for m in measures]
    })

# -----------------------------
# Delete Food Log
# -----------------------------
@member_bp.route('/delete-food-log/<int:log_id>', methods=['POST'])
def delete_food_log(log_id):
    user_id = session.get('user_id')
    if not user_id:
        flash("Please log in first.", "danger")
        return redirect(url_for("auth.login_member"))
    
    # Find the log entry
    log = UserFoodLog.query.get(log_id)
    
    if not log:
        flash("Food log not found.", "danger")
        return redirect(url_for("member.dashboard"))
    
    # Make sure this log belongs to the current user
    if log.user_id != user_id:
        flash("You don't have permission to delete this log.", "danger")
        return redirect(url_for("member.dashboard"))
    
    # Delete the log
    food_name = log.food.name
    db.session.delete(log)
    db.session.commit()
    
    flash(f"Removed {food_name} from your log.", "success")
    return redirect(url_for("member.dashboard"))