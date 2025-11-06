from flask import Blueprint, render_template, session, flash, redirect, request, url_for, jsonify
from app import db
from app.models import (
    User,
    Progress,
    Food,
    UserFoodLog,
    FoodMeasure,
    WorkoutSession,
    WorkoutSet,
    TrainerMeal,
    MemberMeal,
    MemberMealIngredient,
)
from app.services.nutrition import (
    scale_food_nutrients,
    calculate_meal_macros,
    group_meals_by_slot,
    serialize_meal,
    MEAL_SLOT_LABELS,
)
from sqlalchemy import or_, and_
from datetime import datetime, date
import calendar as _calendar

member_bp = Blueprint('member', __name__, url_prefix='/member')

ACTIVITY_LEVELS = [
    (1.2, "Sedentary (1.2)"),
    (1.375, "Lightly Active (1.375)"),
    (1.55, "Moderately Active (1.55)"),
    (1.725, "Very Active (1.725)"),
    (1.9, "Extremely Active (1.9)")
]

# -----------------------------
# Inject user into templates
# -----------------------------
@member_bp.app_context_processor
def inject_user():
    user_id = session.get("user_id")
    if user_id:
        return {"user": User.query.get(user_id)}
    return {}

def _pounds_to_kg(value):
    if value is None:
        return None
    try:
        return float(value) * 0.45359237
    except (TypeError, ValueError):
        return None


def _kg_to_pounds(value):
    if value is None:
        return None
    try:
        return float(value) / 0.45359237
    except (TypeError, ValueError):
        return None


def _latest_weight_lbs(user):
    if not user:
        return None
    entry = (
        Progress.query
        .filter(Progress.user_id == user.id, Progress.weight != None)  # noqa: E711
        .order_by(Progress.date.desc())
        .first()
    )
    if entry and entry.weight:
        try:
            return float(entry.weight)
        except (TypeError, ValueError):
            return None
    return None


def _calculate_bmr(gender, weight_kg, height_cm, age):
    if not all([gender, weight_kg, height_cm, age]):
        return None
    try:
        weight = float(weight_kg)
        height = float(height_cm)
        age_val = int(age)
    except (TypeError, ValueError):
        return None

    gender = str(gender).lower()
    if gender.startswith('f'):
        return (10 * weight) + (6.25 * height) - (5 * age_val) - 161
    return (10 * weight) + (6.25 * height) - (5 * age_val) + 5


def _calculate_calorie_targets(user, weight_lbs=None):
    if not user:
        return None, None

    weight = weight_lbs if weight_lbs is not None else _latest_weight_lbs(user)
    if weight is None:
        return None, None

    bmr = _calculate_bmr(user.gender, _pounds_to_kg(weight), user.height_cm, user.age)
    if bmr is None:
        return None, None

    activity_factor = user.activity_level or 1.2
    maintenance = bmr * activity_factor

    weekly_change = user.weekly_weight_change_lbs or 0
    try:
        weekly_change = float(weekly_change)
    except (TypeError, ValueError):
        weekly_change = 0

    goal = maintenance - (weekly_change * 500)

    # Round to nearest tenth for display/storage consistency
    return round(max(0, maintenance), 1), round(max(0, goal), 1)


def _update_user_calorie_targets(user, weight_lbs=None):
    maintenance, goal = _calculate_calorie_targets(user, weight_lbs)
    user.maintenance_calories = maintenance if maintenance is not None else None
    user.calorie_goal = goal if goal is not None else None

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
    macro_targets = {
        "calories": user.custom_calorie_target or user.calorie_goal,
        "protein": user.custom_protein_target_g,
        "carbs": user.custom_carb_target_g,
        "fats": user.custom_fat_target_g,
    }
    calorie_goal_value = macro_targets["calories"] or user.calorie_goal or 2000

    if user.trainer_id:
        trainer_meals = (
            TrainerMeal.query
            .filter(
                or_(
                    TrainerMeal.member_id == user.id,
                    TrainerMeal.member_id.is_(None),
                    and_(
                        TrainerMeal.trainer_id == user.trainer_id
                    )
                )
            )
            .order_by(TrainerMeal.meal_slot.asc(), TrainerMeal.name.asc())
            .all()
        )
    else:
        trainer_meals = (
            TrainerMeal.query
            .filter(TrainerMeal.member_id == user.id)
            .order_by(TrainerMeal.meal_slot.asc(), TrainerMeal.name.asc())
            .all()
        )
    meal_plan = group_meals_by_slot(trainer_meals) if trainer_meals else {slot: [] for slot in MEAL_SLOT_LABELS}
    member_meals = (
        MemberMeal.query
        .filter_by(user_id=user.id)
        .order_by(MemberMeal.meal_slot.asc(), MemberMeal.name.asc())
        .all()
    )
    member_meal_plan = group_meals_by_slot(member_meals) if member_meals else {slot: [] for slot in MEAL_SLOT_LABELS}

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
    selected_workouts = []

    workout_sessions = (
        WorkoutSession.query
        .filter_by(user_id=user.id)
        .order_by(WorkoutSession.started_at.desc())
        .all()
    )

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

        workout_map = {}
        for sess in workout_sessions:
            dt = getattr(sess, 'completed_at', None) or getattr(sess, 'started_at', None)
            if not dt:
                continue
            try:
                day = dt.date() if isinstance(dt, datetime) else dt
            except Exception:
                continue
            workout_map.setdefault(day, []).append(sess)

        def _format_time(dt_obj):
            if not dt_obj:
                return ''
            try:
                if isinstance(dt_obj, datetime):
                    return dt_obj.strftime('%H:%M')
            except Exception:
                return ''
            return ''

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
                                    scaled = scale_food_nutrients(fl.food, grams_logged)
                                    total_cals += scaled["calories"]
                                    total_protein += scaled["protein"]
                                    total_carbs += scaled["carbs"]
                                    total_fats += scaled["fats"]

                            food_calories = round(total_cals, 1) if total_cals else None
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

                    workouts_for_day = []
                    for sess in workout_map.get(d, []):
                        workouts_for_day.append({
                            'id': sess.id,
                            'summary': sess.summary,
                            'time': _format_time(getattr(sess, 'completed_at', None) or getattr(sess, 'started_at', None)),
                            'template': sess.template.name if getattr(sess, 'template', None) else None,
                        })

                    data = {
                        'weight': weight_val,
                        'food': {
                            'calories': food_calories,
                            'protein': food_protein if 'food_protein' in locals() else None,
                            'carbs': food_carbs if 'food_carbs' in locals() else None,
                            'fats': food_fats if 'food_fats' in locals() else None,
                        } if (food_calories or (('food_protein' in locals() and food_protein) or ('food_carbs' in locals() and food_carbs) or ('food_fats' in locals() and food_fats))) else None,
                        'workouts': workouts_for_day if workouts_for_day else None,
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
                        scaled = scale_food_nutrients(fl.food, grams_logged)
                        tot += scaled["calories"]
                        total_protein += scaled["protein"]
                        total_carbs += scaled["carbs"]
                        total_fats += scaled["fats"]
                selected_food_calories = round(tot, 1) if tot else None
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

            try:
                selected_workouts = []
                for sess in workout_map.get(selected_date, []):
                    workout_sets = (
                        WorkoutSet.query
                        .filter_by(session_id=sess.id)
                        .order_by(WorkoutSet.exercise_name.asc(), WorkoutSet.set_number.asc())
                        .all()
                    )
                    selected_workouts.append({
                        'session': sess,
                        'time': _format_time(getattr(sess, 'completed_at', None) or getattr(sess, 'started_at', None)),
                        'summary': sess.summary,
                        'sets': workout_sets,
                    })
            except Exception:
                selected_workouts = []
        except Exception:
            selected_weight = None
            selected_food_calories = None

    latest_weight_lbs = _latest_weight_lbs(user)
    goal_weight_lbs = _kg_to_pounds(user.goal_weight_kg)

    height_feet = None
    height_inches = None
    if user.height_cm:
        try:
            total_inches = float(user.height_cm) / 2.54
            height_feet = int(total_inches // 12)
            remaining_inches = total_inches - (height_feet * 12)
            height_inches = round(remaining_inches)
            if height_inches == 12:
                height_feet += 1
                height_inches = 0
        except (TypeError, ValueError):
            height_feet = None
            height_inches = None

    profile_bmr = _calculate_bmr(user.gender, _pounds_to_kg(latest_weight_lbs), user.height_cm, user.age)
    recent_weights = []
    if view == 'profile':
        recent_weights = (
            Progress.query
            .filter_by(user_id=user.id)
            .order_by(Progress.date.desc())
            .limit(10)
            .all()
        )

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
        selected_food_items=selected_food_items if 'selected_food_items' in locals() else [],
        selected_workouts=selected_workouts,
        activity_levels=ACTIVITY_LEVELS,
        latest_weight_lbs=latest_weight_lbs,
        height_feet=height_feet,
        height_inches=height_inches,
        goal_weight_lbs=goal_weight_lbs,
        profile_bmr=profile_bmr,
        recent_weights=recent_weights,
        macro_targets=macro_targets,
        calorie_goal_value=calorie_goal_value,
        meal_plan=meal_plan,
        meal_slot_labels=MEAL_SLOT_LABELS,
        member_meal_plan=member_meal_plan,
        today=today
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
def _calculate_daily_totals(user_id: int, target_date: date) -> dict:
    logs = UserFoodLog.query.filter_by(user_id=user_id, log_date=target_date).all()
    totals = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}

    for log in logs:
        scaled = scale_food_nutrients(log.food, log.quantity_in_grams())
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
    scaled = scale_food_nutrients(food, quantity_in_grams)

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


@member_bp.route("/add-meal/<int:meal_id>", methods=["POST"])
def add_meal_to_log(meal_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "Please log in first."}), 403

    today = datetime.utcnow().date()
    meal = TrainerMeal.query.get(meal_id)

    if not meal:
        return jsonify({"status": "error", "message": "Meal not found or unauthorized."}), 404

    member = User.query.get(user_id)
    if meal.member_id and meal.member_id != user_id:
        return jsonify({"status": "error", "message": "Meal not available for this member."}), 403
    if meal.member_id is None:
        if not member or not member.trainer_id:
            return jsonify({"status": "error", "message": "A trainer is required to use this meal."}), 403

    logs_payload = []

    for ingredient in meal.ingredients:
        grams = float(ingredient.quantity_grams or 0.0)
        if grams <= 0:
            continue

        log = UserFoodLog(
            user_id=user_id,
            food_id=ingredient.food_id,
            quantity=grams,
            unit="g",
            log_date=today
        )
        db.session.add(log)
        db.session.flush()

        scaled = scale_food_nutrients(log.food, grams)
        logs_payload.append({
            "id": log.id,
            "food_name": log.food.name if log.food else "Meal Ingredient",
            "quantity": round(grams, 2),
            "unit": "g",
            "calories": round(scaled["calories"], 1),
            "protein": round(scaled["protein"], 1),
            "carbs": round(scaled["carbs"], 1),
            "fats": round(scaled["fats"], 1)
        })

    if not logs_payload:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Meal has no ingredients to log."}), 400

    db.session.commit()

    totals = _calculate_daily_totals(user_id, today)
    totals["fats"] = totals["fat"]

    return jsonify({
        "status": "success",
        "message": f"Added {meal.name} to your log.",
        "logs": logs_payload,
        "totals": totals
    })


@member_bp.route("/meals", methods=["POST"])
def create_member_meal():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "Please log in first."}), 403

    user = User.query.get(user_id)
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"status": "error", "message": "Meal name is required."}), 400

    slot = (data.get("slot") or "meal1").strip().lower()
    if slot not in MEAL_SLOT_LABELS:
        slot = "meal1"

    description = (data.get("description") or "").strip()
    ingredients_payload = data.get("ingredients") or []

    if not ingredients_payload:
        return jsonify({"status": "error", "message": "Add at least one ingredient."}), 400

    meal = MemberMeal(
        user_id=user.id,
        name=name,
        description=description or None,
        meal_slot=slot
    )

    try:
        for idx, item in enumerate(ingredients_payload):
            food_id = item.get("food_id")
            quantity_raw = item.get("quantity")
            unit = (item.get("unit") or "g").strip().lower()

            if not food_id or quantity_raw in (None, ""):
                continue

            try:
                quantity = float(quantity_raw)
            except (TypeError, ValueError):
                return jsonify({"status": "error", "message": "Invalid ingredient quantity."}), 400

            if quantity <= 0:
                return jsonify({"status": "error", "message": "Ingredient quantity must be greater than zero."}), 400

            grams_override = item.get("grams")
            volume_override = item.get("volume_ml")
            try:
                grams_total, volume_ml = convert_to_grams(
                    food_id,
                    quantity,
                    unit,
                    grams_override=_safe_float(grams_override),
                    volume_override=_safe_float(volume_override)
                )
            except Exception as exc:
                return jsonify({"status": "error", "message": f"Unable to convert units: {exc}"}), 400

            ingredient = MemberMealIngredient(
                food_id=food_id,
                quantity_value=quantity,
                quantity_unit=unit,
                quantity_grams=grams_total,
                volume_ml=volume_ml,
                position=idx,
                notes=(item.get("notes") or "").strip() or None
            )
            meal.ingredients.append(ingredient)

        if not meal.ingredients:
            return jsonify({"status": "error", "message": "Add at least one valid ingredient."}), 400

        db.session.add(meal)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Failed to create meal: {exc}"}), 500

    return jsonify({
        "status": "success",
        "meal": serialize_meal(meal)
    })


def _safe_float(value):
    if value in (None, "", "undefined"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@member_bp.route("/meals/<int:meal_id>", methods=["DELETE"])
def delete_member_meal(meal_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "Please log in first."}), 403

    meal = MemberMeal.query.filter_by(id=meal_id, user_id=user_id).first()
    if not meal:
        return jsonify({"status": "error", "message": "Meal not found."}), 404

    db.session.delete(meal)
    db.session.commit()
    return jsonify({"status": "success"})


@member_bp.route("/add-member-meal/<int:meal_id>", methods=["POST"])
def add_member_meal_to_log(meal_id: int):
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"status": "error", "message": "Please log in first."}), 403

    today = datetime.utcnow().date()
    meal = MemberMeal.query.filter_by(id=meal_id, user_id=user_id).first()
    if not meal:
        return jsonify({"status": "error", "message": "Meal not found."}), 404

    logs_payload = []
    for ingredient in meal.ingredients:
        grams = float(ingredient.quantity_grams or 0.0)
        if grams <= 0:
            continue

        log = UserFoodLog(
            user_id=user_id,
            food_id=ingredient.food_id,
            quantity=grams,
            unit="g",
            log_date=today
        )
        db.session.add(log)
        db.session.flush()

        scaled = scale_food_nutrients(log.food, grams)
        logs_payload.append({
            "id": log.id,
            "food_name": log.food.name if log.food else "Meal Ingredient",
            "quantity": round(grams, 2),
            "unit": "g",
            "calories": round(scaled["calories"], 1),
            "protein": round(scaled["protein"], 1),
            "carbs": round(scaled["carbs"], 1),
            "fats": round(scaled["fats"], 1)
        })

    if not logs_payload:
        db.session.rollback()
        return jsonify({"status": "error", "message": "Meal has no ingredients to log."}), 400

    db.session.commit()
    totals = _calculate_daily_totals(user_id, today)
    totals["fats"] = totals["fat"]

    return jsonify({
        "status": "success",
        "message": f"Added {meal.name} to your log.",
        "logs": logs_payload,
        "totals": totals
    })
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

    scaled = scale_food_nutrients(food, grams)
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
# Update Profile Information
# -----------------------------
@member_bp.route('/update-info', methods=['POST'])
def update_info():
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id or role != 'member':
        flash("Please log in as a member.", "danger")
        return redirect(url_for('auth.login_member'))

    user = User.query.get(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('auth.login_member'))

    gender = request.form.get('gender')
    if gender:
        user.gender = gender.lower()
    else:
        user.gender = None

    age_raw = request.form.get('age')
    if age_raw is not None:
        if str(age_raw).strip() == "":
            user.age = None
        else:
            try:
                user.age = int(age_raw)
            except (TypeError, ValueError):
                flash("Please enter a valid age.", "warning")

    # Height handling: prefer centimeters, fall back to feet/inches
    height_cm_raw = request.form.get('height_cm')
    height_updated = False
    if height_cm_raw:
        try:
            height_cm_val = float(height_cm_raw)
            if height_cm_val > 0:
                user.height_cm = height_cm_val
                height_updated = True
        except (TypeError, ValueError):
            flash("Invalid height in centimeters.", "warning")

    if not height_updated:
        feet_raw = request.form.get('height_feet')
        inches_raw = request.form.get('height_inches')
        if feet_raw or inches_raw:
            try:
                feet = int(feet_raw or 0)
                inches = float(inches_raw or 0)
                total_inches = (feet * 12) + inches
                if total_inches > 0:
                    user.height_cm = total_inches * 2.54
            except (TypeError, ValueError):
                flash("Invalid height in feet/inches.", "warning")

    activity_raw = request.form.get('activity_level')
    if activity_raw is not None:
        if str(activity_raw).strip() == "":
            user.activity_level = None
        else:
            try:
                user.activity_level = float(activity_raw)
            except (TypeError, ValueError):
                flash("Please choose a valid activity level.", "warning")

    goal_weight_raw = request.form.get('goal_weight_lbs')
    if goal_weight_raw is not None:
        if str(goal_weight_raw).strip() == "":
            user.goal_weight_kg = None
        else:
            try:
                goal_weight_lbs = float(goal_weight_raw)
                if goal_weight_lbs > 0:
                    user.goal_weight_kg = _pounds_to_kg(goal_weight_lbs)
            except (TypeError, ValueError):
                flash("Invalid goal weight.", "warning")

    weekly_change_raw = request.form.get('weekly_weight_change')
    if weekly_change_raw is not None:
        if str(weekly_change_raw).strip() == "":
            user.weekly_weight_change_lbs = None
        else:
            try:
                weekly_change = float(weekly_change_raw)
                if weekly_change < 0:
                    weekly_change = abs(weekly_change)
                user.weekly_weight_change_lbs = weekly_change
            except (TypeError, ValueError):
                flash("Invalid weekly weight change.", "warning")

    _update_user_calorie_targets(user)
    db.session.commit()

    flash("Profile updated successfully.", "success")
    return redirect(url_for('member.dashboard', view='profile'))


# -----------------------------
# Log Weight
# -----------------------------
@member_bp.route('/log-weight', methods=['POST'])
def log_weight():
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id or role != 'member':
        flash("Please log in as a member.", "danger")
        return redirect(url_for('auth.login_member'))

    user = User.query.get(user_id)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for('auth.login_member'))

    weight_raw = request.form.get('weight_lbs')
    try:
        weight_lbs = float(weight_raw)
    except (TypeError, ValueError):
        flash("Please enter a valid weight.", "warning")
        return redirect(url_for('member.dashboard', view='profile'))

    if weight_lbs <= 0:
        flash("Weight must be greater than zero.", "warning")
        return redirect(url_for('member.dashboard', view='profile'))

    date_raw = request.form.get('weight_date')
    if date_raw:
        try:
            weight_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
        except ValueError:
            flash("Invalid date format for weight entry.", "warning")
            return redirect(url_for('member.dashboard', view='profile'))
    else:
        weight_date = datetime.utcnow().date()

    entry_datetime = datetime.combine(weight_date, datetime.utcnow().time())
    log_entry = Progress(user_id=user.id, date=entry_datetime, weight=weight_lbs)
    db.session.add(log_entry)

    _update_user_calorie_targets(user, weight_lbs=weight_lbs)
    db.session.commit()

    flash("Weight logged successfully.", "success")
    return redirect(url_for('member.dashboard', view='profile'))


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

    return redirect(url_for('template.list_templates'))


@member_bp.route("/get-measures/<int:food_id>")
def get_measures(food_id):
    measures = FoodMeasure.query.filter_by(food_id=food_id).all()
    payload = []
    seen = set()

    for measure in measures:
        if not measure or not measure.grams:
            continue
        name = (measure.measure_name or "").strip().lower()
        if not name or name in seen:
            continue
        seen.add(name)
        payload.append({"measure_name": measure.measure_name, "grams": measure.grams})

    # Always ensure grams and ounces are available as fallbacks
    if "g" not in seen:
        payload.append({"measure_name": "g", "grams": 1})
    if "oz" not in seen:
        payload.append({"measure_name": "oz", "grams": UNIT_TO_GRAMS.get("oz", 28.35)})

    return jsonify({"measures": payload})

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
