from flask import Blueprint, render_template, session, flash, redirect, request, url_for, jsonify
from app import db
from app.models import User, Progress, Food, UserFoodLog, FoodMeasure
from datetime import datetime, date
import calendar as _calendar

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
    # Fetch today's logs + compute totals (default view)
    # -----------------------------
    user_food_logs = UserFoodLog.query.filter_by(user_id=user.id, log_date=today).all()
    totals = _calculate_daily_totals(user.id, today)

    # ----------
    # Calendar support (server-rendered, no JS required)
    # If the client requested view=calendar we will compute calendar_weeks
    # and selected_date so the template can render a full month with
    # per-day weight and food calorie summaries.
    # ----------
    view = request.args.get('view')
    cal_year = request.args.get('year', type=int)
    cal_month = request.args.get('month', type=int)
    sel_day = request.args.get('day')

    selected_date = None
    calendar_weeks = None
    selected_weight = None
    selected_food_calories = None

    if view == 'calendar':
        # default to current month if not provided
        if not cal_year or not cal_month:
            cal_year = today.year
            cal_month = today.month

        # parse selected day if provided (ISO yyyy-mm-dd) else default to today
        try:
            selected_date = datetime.strptime(sel_day, "%Y-%m-%d").date() if sel_day else today
        except Exception:
            selected_date = today

        def _build_calendar_weeks(year, month, user_obj):
            weeks = []
            cal = _calendar.Calendar(firstweekday=6)  # start on Sunday
            for week in cal.monthdatescalendar(year, month):
                week_list = []
                for d in week:
                    in_month = (d.month == month)
                    if not in_month:
                        week_list.append({'iso': '', 'day': '', 'in_month': False, 'data': None})
                        continue

                    iso = d.strftime('%Y-%m-%d')

                    # weight: pick most-recent Progress/WeightLog entry for that date
                    weight_val = None
                    try:
                        # compute per-macro totals for selected day
                        rows = Progress.query.filter_by(user_id=user_obj.id).all()
                        day_rows = []
                        for r in rows:
                            dt = getattr(r, 'date', None) or getattr(r, 'log_date', None)
                            if dt is None:
                                continue
                            try:
                                if isinstance(dt, datetime):
                                    match = (dt.date() == d)
                                else:
                                    match = (dt == d)
                            except Exception:
                                match = False
                            if match:
                                day_rows.append(r)
                        if day_rows:
                            def _ord_key(x):
                                return getattr(x, 'created_at', None) or getattr(x, 'id', 0)
                            weight_entry = max(day_rows, key=_ord_key)
                            weight_val = float(getattr(weight_entry, 'weight')) if getattr(weight_entry, 'weight', None) is not None else None
                    except Exception:
                        weight_val = None

                    # food calories: sum UserFoodLog.quantity (grams) scaled by food.calories per serving
                    food_calories = None
                    try:
                        # robust per-row date matching (support Date and DateTime columns)
                        all_fls = UserFoodLog.query.filter_by(user_id=user_obj.id).all()
                        fls = []
                        for f in all_fls:
                            dt = getattr(f, 'date', None) or getattr(f, 'log_date', None)
                            if dt is None:
                                continue
                            try:
                                if isinstance(dt, datetime):
                                    match = (dt.date() == d)
                                else:
                                    match = (dt == d)
                            except Exception:
                                match = False
                            if match:
                                fls.append(f)

                        if fls:
                            total_cals = 0.0
                            total_protein = 0.0
                            total_carbs = 0.0
                            total_fats = 0.0
                            for fl in fls:
                                if getattr(fl, 'food', None):
                                    grams_logged = fl.quantity_in_grams() if hasattr(fl, 'quantity_in_grams') else getattr(fl, 'quantity', 0)
                                    scaled = _scale_food_nutrients(fl.food, grams_logged)
                                    total_cals += scaled["calories"]
                                    total_protein += scaled["protein"]
                                    total_carbs += scaled["carbs"]
                                    total_fats += scaled["fats"]

                            food_calories = int(total_cals) if total_cals else None
                            food_protein = round(total_protein, 1) if total_protein else None
                            food_carbs = round(total_carbs, 1) if total_carbs else None
                            food_fats = round(total_fats, 1) if total_fats else None
                        else:
                            food_calories = None
                            food_protein = None
                            food_carbs = None
                            food_fats = None
                    except Exception:
                        food_calories = None
                        items = []

                    data = {
                        'weight': weight_val,
                        'food': {
                            'calories': food_calories,
                            'protein': food_protein if 'food_protein' in locals() else None,
                            'carbs': food_carbs if 'food_carbs' in locals() else None,
                            'fats': food_fats if 'food_fats' in locals() else None,
                        } if (food_calories or (('food_protein' in locals() and food_protein) or ('food_carbs' in locals() and food_carbs) or ('food_fats' in locals() and food_fats))) else None,
                    }

                    week_list.append({'iso': iso, 'day': d.day, 'in_month': True, 'data': data})
                weeks.append(week_list)
            return weeks

        calendar_weeks = _build_calendar_weeks(cal_year, cal_month, user)

        # selected-day details: weight and totals for the selected_date
        try:
            # selected weight (robust match)
            sel_weight = None
            try:
                rows = Progress.query.filter_by(user_id=user.id).all()
                day_rows = []
                for r in rows:
                    dt = getattr(r, 'date', None) or getattr(r, 'log_date', None)
                    if dt is None:
                        continue
                    try:
                        if isinstance(dt, datetime):
                            match = (dt.date() == selected_date)
                        else:
                            match = (dt == selected_date)
                    except Exception:
                        match = False
                    if match:
                        day_rows.append(r)
                if day_rows:
                    def _ord_key(x):
                        return getattr(x, 'created_at', None) or getattr(x, 'id', 0)
                    weight_entry = max(day_rows, key=_ord_key)
                    sel_weight = float(getattr(weight_entry, 'weight')) if getattr(weight_entry, 'weight', None) is not None else None
            except Exception:
                sel_weight = None
            selected_weight = sel_weight

            # selected food totals (robust per-row matching)
            try:
                all_fls = UserFoodLog.query.filter_by(user_id=user.id).all()
                tot = 0.0
                total_protein = 0.0
                total_carbs = 0.0
                total_fats = 0.0
                for fl in all_fls:
                    dt = getattr(fl, 'date', None) or getattr(fl, 'log_date', None)
                    if dt is None:
                        continue
                    try:
                        if isinstance(dt, datetime):
                            match = (dt.date() == selected_date)
                        else:
                            match = (dt == selected_date)
                    except Exception:
                        match = False
                    if not match:
                        continue
                    if getattr(fl, 'food', None):
                        grams_logged = fl.quantity_in_grams() if hasattr(fl, 'quantity_in_grams') else getattr(fl, 'quantity', 0)
                        scaled = _scale_food_nutrients(fl.food, grams_logged)
                        tot += scaled["calories"]
                        total_protein += scaled["protein"]
                        total_carbs += scaled["carbs"]
                        total_fats += scaled["fats"]
                selected_food_calories = int(tot) if tot else None
                selected_food_protein = round(total_protein, 1) if total_protein else None
                selected_food_carbs = round(total_carbs, 1) if total_carbs else None
                selected_food_fats = round(total_fats, 1) if total_fats else None
                selected_food_items = []
            except Exception:
                selected_food_calories = None
                selected_food_items = []
                selected_food_protein = None
                selected_food_carbs = None
                selected_food_fats = None
        except Exception:
            selected_weight = None
            selected_food_calories = None

    return render_template(
        "dashboard-member.html",
        user=user,
        user_food_logs=user_food_logs,
        totals=totals,
        search_results=search_results,
        UNIT_TO_GRAMS=UNIT_TO_GRAMS,
        # calendar context (may be None when not requested)
        view=view,
        cal_year=cal_year,
        cal_month=cal_month,
        calendar_weeks=calendar_weeks,
        selected_date=selected_date,
        selected_weight=selected_weight,
        selected_food_calories=selected_food_calories,
        selected_food_protein=selected_food_protein if 'selected_food_protein' in locals() else None,
        selected_food_carbs=selected_food_carbs if 'selected_food_carbs' in locals() else None,
        selected_food_fats=selected_food_fats if 'selected_food_fats' in locals() else None,
        selected_food_items=selected_food_items if 'selected_food_items' in locals() else []
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

def _serving_grams(food: Food) -> float:
    """Return the gram weight that nutrient data is based on for a food."""
    for value in (getattr(food, "serving_size", None), getattr(food, "grams_per_unit", None)):
        if value and value > 0:
            return float(value)
    return 100.0


def _scale_food_nutrients(food: Food, quantity_in_grams: float) -> dict:
    """Scale a food's macro profile to a quantity in grams, inferring calories when missing."""
    if not food:
        return {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fats": 0.0}
    grams = float(quantity_in_grams or 0.0)
    serving_grams = _serving_grams(food)
    factor = grams/serving_grams if serving_grams else 0.0

    base_protein = float(food.protein_g or 0.0)
    base_carbs = float(food.carbs_g or 0.0)
    base_fats = float(food.fats_g or 0.0)
    base_calories = float(food.calories or 0.0)


    macro_calories = (base_protein * 4) + (base_carbs * 4) + (base_fats * 9)
    adjusted_calories = base_calories

    if macro_calories:
        if not adjusted_calories:
            adjusted_calories = macro_calories
        else:
            ratio = adjusted_calories / macro_calories if macro_calories else 1
            if ratio > 2 or ratio < 0.5:    
                adjusted_calories = macro_calories


    return {
        "calories": adjusted_calories * factor,
        "protein": base_protein * factor,
        "carbs": base_carbs * factor,
        "fats": base_fats * factor
    }


def _calculate_daily_totals(user_id: int, target_date: date) -> dict:
    logs = UserFoodLog.query.filter_by(user_id=user_id, log_date=target_date).all()
    totals = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}

    for log in logs:
        scaled = _scale_food_nutrients(log.food, log.quantity_in_grams())
        totals["calories"] += scaled["calories"]
        totals["protein"] += scaled["protein"]
        totals["carbs"] += scaled["carbs"]
        totals["fat"] += scaled["fats"]

    return {key: round(value, 1) for key, value in totals.items()}


@member_bp.route("/get-totals")
def get_totals():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "Please log in first."}), 403

    today = datetime.utcnow().date()
    totals = _calculate_daily_totals(user_id, today)
    totals["fats"] = totals["fat"]
    return jsonify(totals)


def scaled_macros(food: Food, quantity_in_grams: float):
    scaled = _scale_food_nutrients(food, quantity_in_grams)

    return {
        "calories": round(scaled["calories"], 1),
        "protein": round(scaled["protein"], 1),
        "carbs": round(scaled["carbs"], 1),
        "fats": round(scaled["fats"], 1),
    }

def scale_nutrients(food_id, quantity, unit):
    measure = FoodMeasure.query.filter_by(food_id=food_id, measure_name=unit).first()
    if measure:
        grams = quantity * measure.grams
    else:
        # fallback to 100g base if unit is unknown
        grams = quantity

    food = Food.query.get(food_id)
    scaled = scaled_macros(food, grams)  # assuming macros stored per 100g

    return {
        "calories": round(scaled["calories"], 1),
        "protein_g": round(scaled["protein"], 1),
        "carbs": round(scaled["carbs"], 1),
        "fats": round(scaled["fats"], 1)
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
            scaled = scaled_macros(food, quantity_in_grams) 

            results.append({
                "id": food.id,
                "name": food.name,
                "calories": round(scaled["calories"], 1),
                "protein_g": round(scaled["protein"], 1),
                "carbs": round(scaled["carbs"], 1),
                "fats": round(scaled["fats"], 1),
                "serving_size": food.serving_size,
                "serving_unit": food.serving_unit
            })

    return jsonify({"results": results})

@member_bp.route("/log-food", methods=["POST"])
def log_food():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "Please log in first."}), 403

    data = request.form if request.form else request.get_json(silent=True) or {}

    quantity_raw = data.get("log_quantity") or data.get("quantity")
    unit_input = (data.get("unit") or "g").strip().lower()
    food_id = data.get("food_id")

    try:
        quantity = float(quantity_raw)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "Please enter a valid quantity."}), 400

    if quantity <= 0:
        return jsonify({"status": "error", "message": "Quantity must be greater than zero."}), 400

    today = datetime.utcnow().date()
    food = None
    created_food = False

    if food_id:
        food = Food.query.get(int(food_id))
        if not food:
            return jsonify({"status": "error", "message": "Selected food not found."}), 404
    else:
        search_name = (data.get("food_name") or data.get("food_search") or "").strip()
        if not search_name:
            return jsonify({"status": "error", "message": "Please select a food to log."}), 400

        custom_fields = [data.get("calories"), data.get("protein_g"), data.get("carbs_g"), data.get("fats_g")]
        has_custom_macros = any(value not in (None, "", "0", "0.0") for value in custom_fields)

        if has_custom_macros:
            try:
                calories = float(data.get("calories") or 0)
                protein_g = float(data.get("protein_g") or 0)
                carbs_g = float(data.get("carbs_g") or 0)
                fats_g = float(data.get("fats_g") or 0)
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "Invalid nutrient values for custom food."}), 400

            food = Food(
                name=search_name,
                calories=calories or None,
                protein_g=protein_g or None,
                carbs_g=carbs_g or None,
                fats_g=fats_g or None,
                source_id=None,
                serving_size=100,
                serving_unit="g",
                grams_per_unit=100
            )
            db.session.add(food)
            db.session.commit()
            created_food = True
        else:
            food = Food.query.filter(Food.name.ilike(f"%{search_name}%")).first()
            if not food:
                return jsonify({"status": "error", "message": "No matching foods found."}), 404

    measure = None
    if food and food.id:
        measure = FoodMeasure.query.filter_by(food_id=food.id, measure_name=unit_input).first()

    if measure:
        grams = quantity * measure.grams
    elif unit_input in UNIT_TO_GRAMS:
        grams = quantity * UNIT_TO_GRAMS[unit_input]
    else:
        grams = quantity

    log = UserFoodLog(
        user_id=user_id,
        food_id=food.id,
        quantity=grams,
        unit="g",
        log_date=today
    )
    db.session.add(log)
    db.session.commit()

    scaled = _scale_food_nutrients(food, grams)
    totals = _calculate_daily_totals(user_id, today)
    totals["fats"] = totals["fat"]

    message = f"Added {quantity:g} {unit_input} of {food.name}!"
    log_payload = {
        "id": log.id,
        "food_name": food.name,
        "quantity": round(log.quantity, 2),
        "unit": log.unit,
        "calories": round(scaled["calories"], 1),
        "protein": round(scaled["protein"], 1),
        "carbs": round(scaled["carbs"], 1),
        "fats": round(scaled["fats"], 1)
    }

    return jsonify({
        "status": "success",
        "message": message,
        "log": log_payload,
        "totals": totals,
        "created_food": created_food
    })

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
        return jsonify({"status": "error", "message": "Please log in first."}), 403

    log = UserFoodLog.query.get(log_id)
    if not log or log.user_id != user_id:
        return jsonify({"status": "error", "message": "Log not found or unauthorized."}), 404

    food_name = log.food.name
    db.session.delete(log)
    db.session.commit()

    return jsonify({"status": "success", "message": f"Removed {food_name} from your log."})


# -----------------------------
# Log out
# -----------------------------
@member_bp.route("/logout")
def logout():
    session.clear()  # Clears the entire session
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("auth.login_member"))
