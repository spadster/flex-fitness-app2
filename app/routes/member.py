# ...existing code...
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import date, datetime
import calendar as _calendar

from app import db
import app.models as models

member = Blueprint('member', __name__, url_prefix='/member')
member_bp = member   # export alias so other modules that import "member_bp" won't fail
# ...existing code...

UNIT_TO_GRAMS = {
    "g": 1,
    "kg": 1000,
    "oz": 28.35,
    "lb": 453.592,
    "tsp": 4.2,
    "tbsp": 14.3,
    "cup": 240
}

def _get_model(name):
    return getattr(models, name, None)

def _get_attr(obj, candidates, default=None):
    for n in candidates:
        if hasattr(obj, n):
            return getattr(obj, n)
    return default

def _get_user():
    uid = session.get('user_id')
    if not uid:
        return None
    User = _get_model('User')
    if not User:
        return None
    return User.query.get(uid)

@member.app_context_processor
def inject_user():
    user_id = session.get('user_id')
    if not user_id:
        return {}
    User = _get_model('User')
    if not User:
        return {}
    return {"user": User.query.get(user_id)}

def _parse_iso_date(s, fallback=None):
    if not s:
        return fallback
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return fallback

def _get_measures_for_food(food_id):
    FoodMeasure = _get_model('FoodMeasure')
    if not FoodMeasure:
        return []
    try:
        rows = FoodMeasure.query.filter_by(food_id=food_id).all()
        return [{"measure_name": getattr(r, "measure_name", None), "grams": getattr(r, "grams", None)} for r in rows]
    except Exception:
        return []

def _grams_from_quantity_unit(food_id, quantity, unit):
    unit = (unit or "g").lower()
    FoodMeasure = _get_model('FoodMeasure')
    if FoodMeasure:
        try:
            m = FoodMeasure.query.filter_by(food_id=food_id, measure_name=unit).first()
            if m and getattr(m, "grams", None):
                return float(quantity) * float(getattr(m, "grams"))
        except Exception:
            pass
    grams_per_unit = UNIT_TO_GRAMS.get(unit, None)
    if grams_per_unit is not None:
        return float(quantity) * grams_per_unit
    try:
        return float(quantity)
    except Exception:
        return 0.0

# -----------------------------
# Search Foods API (JSON)
# -----------------------------
@member.route("/search-foods")
def search_foods():
    query = (request.args.get("q") or "").strip()
    unit = request.args.get("unit", "g")
    try:
        quantity = float(request.args.get("quantity", 1))
    except Exception:
        quantity = 1.0

    results = []
    Food = _get_model('Food')
    if query and Food:
        try:
            foods = Food.query.filter(Food.name != None).filter(Food.name.ilike(f"%{query}%")).limit(10).all()
            for food in foods:
                serving_size = _get_attr(food, ['serving_size', 'serving_grams', 'servingSize'], 100) or 100
                serving_unit = _get_attr(food, ['serving_unit', 'servingUnit'], 'g') or 'g'
                calories = _get_attr(food, ['calories', 'kcal'], 0) or 0
                protein = _get_attr(food, ['protein', 'protein_g'], 0) or 0
                carbs = _get_attr(food, ['carbs', 'carbs_g'], 0) or 0
                fats = _get_attr(food, ['fat', 'fats_g', 'fats_g'], 0) or 0

                grams_per_unit = UNIT_TO_GRAMS.get(unit.lower(), 1)
                fm = _get_model('FoodMeasure')
                if fm:
                    measure = fm.query.filter_by(food_id=getattr(food, 'id', None), measure_name=unit).first()
                    if measure and getattr(measure, 'grams', None):
                        grams_per_unit = getattr(measure, 'grams')

                quantity_in_grams = quantity * grams_per_unit
                factor = quantity_in_grams / (serving_size or 100)
                results.append({
                    "id": getattr(food, 'id', None),
                    "name": getattr(food, 'name', None),
                    "calories": round(float(calories) * factor, 1),
                    "protein_g": round(float(protein) * factor, 1),
                    "carbs_g": round(float(carbs) * factor, 1),
                    "fats_g": round(float(fats) * factor, 1),
                    "serving_size": serving_size,
                    "serving_unit": serving_unit
                })
        except Exception:
            results = []

    return jsonify({"results": results})

@member.route("/get-measures/<int:food_id>")
def get_measures(food_id):
    measures = _get_measures_for_food(food_id)
    return jsonify({"measures": measures})

# -----------------------------
# Add / Custom Add Food API
# -----------------------------
@member.route("/add-food", methods=["POST"])
def add_food():
    user = _get_user()
    if not user:
        flash("Please log in first.", "danger")
        return redirect(url_for("auth.login_member"))

    Food = _get_model('Food')
    FoodLog = _get_model('FoodLog') or _get_model('UserFoodLog')
    FoodMeasure = _get_model('FoodMeasure')

    food_id = request.form.get("food_id")
    food_name = (request.form.get("food_name") or request.form.get("food_search") or "").strip()
    unit = (request.form.get("unit") or "g").strip().lower()
    qty_raw = request.form.get("log_quantity") or request.form.get("quantity") or request.form.get("quantity_g") or "0"
    try:
        qty_input = float(qty_raw)
    except Exception:
        qty_input = 0.0

    if not food_id and food_name and Food:
        top = Food.query.filter(Food.name.ilike(f"%{food_name}%")).first()
        if top:
            food_id = getattr(top, 'id', None)

    if not Food:
        flash("Food model not available.", "danger")
        return redirect(url_for("member.dashboard"))

    if not food_id and (request.form.get("calories") or request.form.get("protein_g") or request.form.get("carbs_g") or request.form.get("fats_g")):
        try:
            calories = float(request.form.get("calories") or 0)
            protein = float(request.form.get("protein_g") or request.form.get("protein") or 0)
            carbs = float(request.form.get("carbs_g") or request.form.get("carbs") or 0)
            fats = float(request.form.get("fats_g") or request.form.get("fats") or 0)
        except Exception:
            calories = protein = carbs = fats = 0.0

        new_food = Food(
            name=food_name or "Custom Food",
            **({} if not hasattr(Food, 'calories') else {'calories': calories}),
            **({} if not hasattr(Food, 'protein_g') else {'protein_g': protein}),
            **({} if not hasattr(Food, 'carbs_g') else {'carbs_g': carbs}),
            **({} if not hasattr(Food, 'fats_g') else {'fats_g': fats})
        )
        db.session.add(new_food)
        db.session.commit()
        food_id = getattr(new_food, 'id', None)

    if not food_id:
        flash("No food selected to add.", "warning")
        return redirect(url_for("member.dashboard"))

    grams = _grams_from_quantity_unit(int(food_id), qty_input, unit)

    if FoodLog:
        try:
            kwargs = {'user_id': user.id, 'food_id': int(food_id)}
            kwargs['quantity'] = grams
            if hasattr(FoodLog, 'date'):
                kwargs['date'] = datetime.utcnow().date()
            else:
                kwargs['log_date'] = datetime.utcnow().date()
            if hasattr(FoodLog, 'unit'):
                kwargs['unit'] = 'g'
            log_obj = FoodLog(**kwargs)
            db.session.add(log_obj)
            db.session.commit()
            flash("Food added.", "success")
        except Exception:
            db.session.rollback()
            flash("Failed to add food log.", "danger")
    else:
        flash("Food logging not supported (model missing).", "danger")

    return redirect(url_for("member.dashboard"))

# -----------------------------
# Delete Food Log (support both path styles)
# -----------------------------
@member.route('/delete-food-log/<int:log_id>', methods=['POST'])
@member.route('/delete_food_log/<int:log_id>', methods=['POST'])
def delete_food_log(log_id):
    user = _get_user()
    if not user:
        flash("Please log in first.", "danger")
        return redirect(url_for("auth.login_member"))

    FoodLog = _get_model('FoodLog') or _get_model('UserFoodLog')
    if not FoodLog:
        flash("Food logging not available.", "danger")
        return redirect(url_for("member.dashboard"))

    log = FoodLog.query.get(log_id)
    if not log:
        flash("Food log not found.", "danger")
        return redirect(url_for("member.dashboard"))

    owner_id = getattr(log, 'user_id', None)
    if owner_id != user.id:
        flash("You don't have permission to delete this log.", "danger")
        return redirect(url_for("member.dashboard"))

    try:
        food_name = _get_attr(getattr(log, 'food', None), ['name'], 'item')
        db.session.delete(log)
        db.session.commit()
        flash(f"Removed {food_name} from your log.", "success")
    except Exception:
        db.session.rollback()
        flash("Failed to remove log.", "danger")

    return redirect(url_for("member.dashboard"))

# -----------------------------
# Calendar builder (adapted to your models)
# -----------------------------
def _build_calendar_weeks(year, month, user):
    FoodLog = _get_model('FoodLog') or _get_model('UserFoodLog')
    WeightLog = _get_model('WeightLog') or _get_model('Progress')
    ExerciseLog = _get_model('ExerciseLog') or _get_model('Exercise')

    cal = _calendar.Calendar(firstweekday=6)
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        week_list = []
        for d in week:
            in_month = (d.month == month)
            if not in_month:
                week_list.append({'iso': '', 'day': '', 'in_month': False, 'data': None})
                continue

            iso = d.strftime('%Y-%m-%d')

            # weight (Progress.date is DateTime in your models)
            weight = None
            if WeightLog:
                try:
                    rows = WeightLog.query.filter_by(user_id=user.id).all()
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
                        weight = float(getattr(weight_entry, 'weight')) if getattr(weight_entry, 'weight', None) is not None else None
                except Exception:
                    weight = None

            # food calories (UserFoodLog.log_date exists)
            food_calories = None
            if FoodLog:
                try:
                    # fetch this user's food-logs and match each row's date robustly (date or datetime)
                    all_fls = FoodLog.query.filter_by(user_id=user.id).all()
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
                        total = 0.0
                        for fl in fls:
                            qty_factor = (getattr(fl, 'quantity', 0) or 0) / 100.0
                            if getattr(fl, 'food', None):
                                total += qty_factor * (getattr(fl.food, 'calories', 0) or 0)
                        food_calories = int(total) if total else None
                except Exception:
                    food_calories = None

            # exercises (robust per-row date matching)
            exercises = []
            if ExerciseLog:
                try:
                    all_ex = ExerciseLog.query.filter_by(user_id=user.id).all()
                    for ex in all_ex:
                        dt = getattr(ex, 'date', None) or getattr(ex, 'log_date', None)
                        if dt is None:
                            continue
                        try:
                            if isinstance(dt, datetime):
                                match = (dt.date() == d)
                            else:
                                match = (dt == d)
                        except Exception:
                            match = False
                        if not match:
                            continue
                        exercises.append({
                            'name': getattr(ex, 'name', getattr(ex, 'exercise_name', 'Exercise')),
                            'reps': getattr(ex, 'reps', None),
                            'notes': getattr(ex, 'notes', None)
                        })
                except Exception:
                    exercises = []

            summary_parts = []
            if weight is not None:
                summary_parts.append(f"{weight} kg")
            if food_calories:
                summary_parts.append(f"{food_calories} kcal")
            if exercises:
                summary_parts.append(f"{len(exercises)} ex")

            data = {
                'weight': weight,
                'food': {'calories': food_calories} if food_calories else None,
                'exercises': exercises,
                'summary': ' • '.join(summary_parts) if summary_parts else None
            }

            week_list.append({'iso': iso, 'day': d.day, 'in_month': True, 'data': data})
        weeks.append(week_list)
    return weeks

# -----------------------------
# Dashboard view
# -----------------------------
@member.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    user = _get_user()
    if not user:
        flash("Please log in to access the member dashboard.")
        return redirect(url_for('auth.login_member'))

    Food = _get_model('Food')
    FoodLog = _get_model('FoodLog') or _get_model('UserFoodLog')
    WeightLog = _get_model('WeightLog') or _get_model('Progress')
    ExerciseLog = _get_model('ExerciseLog') or _get_model('Exercise')

    # ...existing code...
    if request.method == 'POST':
        action = request.form.get('action', '')
        target_date = _parse_iso_date(request.form.get('date'), fallback=date.today())

        if action == 'add_food':
            name = (request.form.get('food_search') or '').strip()
            qty_raw = request.form.get('quantity') or '0'
            try:
                qty = float(qty_raw)
            except Exception:
                flash('Invalid quantity', 'danger')
                return redirect(url_for('member.dashboard', year=target_date.year, month=target_date.month, day=target_date.strftime('%Y-%m-%d')))
            if not Food or not FoodLog:
                flash('Food logging not available (model missing).', 'danger')
                return redirect(url_for('member.dashboard'))
            food = Food.query.filter(Food.name.ilike(f"%{name}%")).first() if name else None
            if not food:
                flash('Food not found', 'warning')
                return redirect(url_for('member.dashboard', year=target_date.year, month=target_date.month, day=target_date.strftime('%Y-%m-%d')))

            # determine date field name and normalize a python date to remove ambiguity
            use_date_field = 'date' if hasattr(FoodLog, 'date') else 'log_date'
            target_log_date = target_date

            # remove duplicates for same user + food + day
            try:
                if use_date_field == 'date':
                    existing = FoodLog.query.filter_by(user_id=user.id, food_id=food.id).all()
                    for e in existing:
                        dt = getattr(e, 'date', None) or getattr(e, 'log_date', None)
                        if dt is None:
                            continue
                        if isinstance(dt, datetime):
                            match = (dt.date() == target_log_date)
                        else:
                            match = (dt == target_log_date)
                        if match:
                            db.session.delete(e)
                else:
                    # log_date is a date column — safe to filter
                    FoodLog.query.filter_by(user_id=user.id, food_id=food.id, log_date=target_log_date).delete(synchronize_session=False)
                db.session.flush()
            except Exception:
                db.session.rollback()

            # insert new log (quantity in grams or as provided earlier)
            if hasattr(FoodLog, 'date'):
                fl = FoodLog(user_id=user.id, food_id=food.id, quantity=qty, date=target_log_date)
            else:
                fl = FoodLog(user_id=user.id, food_id=food.id, quantity=qty, log_date=target_log_date)
            db.session.add(fl)
            db.session.commit()
            flash('Food logged', 'success')
            return redirect(url_for('member.dashboard', year=target_date.year, month=target_date.month, day=target_date.strftime('%Y-%m-%d')))

        if action == 'add_weight':
            w_raw = request.form.get('weight')
            try:
                w = float(w_raw)
            except Exception:
                flash('Invalid weight', 'danger')
                return redirect(url_for('member.dashboard'))
            if not WeightLog:
                flash('Weight logging not available (model missing).', 'danger')
                return redirect(url_for('member.dashboard'))

            # remove any existing weight entries for this user/date
            try:
                existing = WeightLog.query.filter_by(user_id=user.id).all()
                for e in existing:
                    dt = getattr(e, 'date', None) or getattr(e, 'log_date', None)
                    if dt is None:
                        continue
                    try:
                        if isinstance(dt, datetime):
                            match = (dt.date() == target_date)
                        else:
                            match = (dt == target_date)
                    except Exception:
                        match = False
                    if match:
                        db.session.delete(e)
                db.session.flush()
            except Exception:
                db.session.rollback()

            if hasattr(WeightLog, 'date'):
                wl = WeightLog(user_id=user.id, weight=w, date=target_date)
            else:
                wl = WeightLog(user_id=user.id, weight=w, log_date=target_date)
            db.session.add(wl)
            db.session.commit()
            flash('Weight logged', 'success')
            return redirect(url_for('member.dashboard', year=target_date.year, month=target_date.month, day=target_date.strftime('%Y-%m-%d')))

        if action == 'add_exercise':
            ex_name = (request.form.get('exercise_name') or '').strip()
            reps_raw = request.form.get('reps')
            notes = request.form.get('notes')
            try:
                reps = int(reps_raw) if reps_raw else None
            except Exception:
                reps = None
            if not ExerciseLog:
                flash('Exercise logging not available (model missing).', 'danger')
                return redirect(url_for('member.dashboard'))

            # remove duplicates: same user, same name, same date
            try:
                existing = ExerciseLog.query.filter_by(user_id=user.id).all()
                for e in existing:
                    dt = getattr(e, 'date', None) or getattr(e, 'log_date', None)
                    if dt is None:
                        continue
                    try:
                        if isinstance(dt, datetime):
                            match = (dt.date() == target_date)
                        else:
                            match = (dt == target_date)
                    except Exception:
                        match = False
                    if match and (getattr(e, 'name', '').strip().lower() == ex_name.strip().lower()):
                        db.session.delete(e)
                db.session.flush()
            except Exception:
                db.session.rollback()

            ex_kwargs = {'user_id': user.id, 'name': ex_name, 'date': target_date} if hasattr(ExerciseLog, 'date') else {'user_id': user.id, 'name': ex_name, 'log_date': target_date}
            if reps is not None:
                ex_kwargs['reps'] = reps
            if hasattr(ExerciseLog, 'notes'):
                ex_kwargs['notes'] = notes
            ex = ExerciseLog(**ex_kwargs)
            db.session.add(ex)
            db.session.commit()
            flash('Exercise logged', 'success')
            return redirect(url_for('member.dashboard', year=target_date.year, month=target_date.month, day=target_date.strftime('%Y-%m-%d')))

# ...existing code...

    # GET
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if not year or not month:
        today = datetime.utcnow().date()
        year = today.year
        month = today.month
    else:
        today = datetime.utcnow().date()

    sel_day = request.args.get('day')
    selected_date = _parse_iso_date(sel_day, fallback=today)

    # --- robust: gather food logs for selected_date (handle Date / DateTime / different column names)
    user_food_logs = []
    totals = {'calories': 0.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 0.0}
    if FoodLog:
        try:
            all_fls = FoodLog.query.filter_by(user_id=user.id).all()
            for f in all_fls:
                dt = getattr(f, 'date', None) or getattr(f, 'log_date', None)
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
                user_food_logs.append(f)

            # normalize Food attributes for templates and compute totals
            for fl in user_food_logs:
                food = getattr(fl, 'food', None)
                if food:
                    if not hasattr(food, 'protein'):
                        setattr(food, 'protein', getattr(food, 'protein_g', getattr(food, 'protein', 0)))
                    if not hasattr(food, 'carbs'):
                        setattr(food, 'carbs', getattr(food, 'carbs_g', getattr(food, 'carbs', 0)))
                    if not hasattr(food, 'fat'):
                        setattr(food, 'fat', getattr(food, 'fats_g', getattr(food, 'fat', 0)))
                    qty_factor = (getattr(fl, 'quantity', 0) or 0) / 100.0
                    totals['calories'] += qty_factor * (getattr(food, 'calories', 0) or 0)
                    totals['protein']  += qty_factor * (getattr(food, 'protein', 0) or 0)
                    totals['carbs']    += qty_factor * (getattr(food, 'carbs', 0) or 0)
                    totals['fat']      += qty_factor * (getattr(food, 'fat', 0) or 0)
        except Exception:
            user_food_logs = []
            totals = {'calories': 0.0, 'protein': 0.0, 'carbs': 0.0, 'fat': 0.0}

    # --- selected day weight (pick most-recent entry for that day)
    selected_weight = None
    if WeightLog:
        try:
            rows = WeightLog.query.filter_by(user_id=user.id).all()
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
                selected_weight = float(getattr(weight_entry, 'weight')) if getattr(weight_entry, 'weight', None) is not None else None
        except Exception:
            selected_weight = None

    # --- selected day exercises (robust date matching)
    selected_exercises = []
    if ExerciseLog:
        try:
            all_ex = ExerciseLog.query.filter_by(user_id=user.id).all()
            for ex in all_ex:
                dt = getattr(ex, 'date', None) or getattr(ex, 'log_date', None)
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
                selected_exercises.append({
                    'id': getattr(ex, 'id', None),
                    'name': getattr(ex, 'name', getattr(ex, 'exercise_name', None)),
                    'reps': getattr(ex, 'reps', None),
                    'notes': getattr(ex, 'notes', None)
                })
        except Exception:
            selected_exercises = []

    calendar_weeks = _build_calendar_weeks(year, month, user)

    # weight history (Progress.date is DateTime)
    weight_history = []
    WL = _get_model('Progress') or _get_model('WeightLog')
    if WL:
        try:
            raw = WL.query.filter_by(user_id=user.id).filter(getattr(WL, 'weight').isnot(None)).order_by(getattr(WL, 'date').desc()).limit(30).all()
            hist = []
            for w in raw:
                dt = getattr(w, 'date', None) or getattr(w, 'log_date', None)
                if isinstance(dt, datetime):
                    ds = dt.date().strftime('%Y-%m-%d')
                elif hasattr(dt, 'strftime'):
                    ds = dt.strftime('%Y-%m-%d')
                else:
                    ds = None
                if ds:
                    hist.append((ds, float(getattr(w, 'weight'))))
            weight_history = list(reversed(hist))
        except Exception:
            weight_history = []

    return render_template(
        'dashboard-member.html',
        user=user,
        user_food_logs=user_food_logs,
        totals=totals,
        selected_weight=selected_weight,
        selected_exercises=selected_exercises,
        cal_year=year,
        cal_month=month,
        calendar_weeks=calendar_weeks,
        today=today,
        selected_date=selected_date,
        weight_history=weight_history
    )

# -----------------------------
# Debug endpoint
# -----------------------------
@member.route("/debug-data")
def debug_data():
    user = _get_user()
    if not user:
        return jsonify({"error": "no user in session"}), 401

    FoodLog = _get_model('FoodLog') or _get_model('UserFoodLog')
    WeightLog = _get_model('WeightLog') or _get_model('Progress')
    ExerciseLog = _get_model('ExerciseLog') or _get_model('Exercise')

    out = {"user_id": user.id, "now": datetime.utcnow().isoformat()}

    def summarize(qrows, attrs):
        res = []
        for r in qrows:
            item = {}
            for a in attrs:
                item[a] = getattr(r, a, None)
            item["food_name"] = getattr(getattr(r, "food", None), "name", None)
            res.append(item)
        return res

    try:
        if FoodLog:
            rows = FoodLog.query.filter_by(user_id=user.id).order_by(getattr(FoodLog, 'id').desc()).limit(20).all()
            out["food_logs_recent"] = summarize(rows, ['id', 'quantity', 'unit', 'log_date', 'date', 'food_id'])
        else:
            out["food_logs_recent"] = "FoodLog model not found"
    except Exception as e:
        out["food_logs_error"] = str(e)

    try:
        if WeightLog:
            rows = WeightLog.query.filter_by(user_id=user.id).order_by(getattr(WeightLog, 'id').desc()).limit(20).all()
            out["weight_logs_recent"] = summarize(rows, ['id', 'weight', 'date', 'log_date'])
        else:
            out["weight_logs_recent"] = "WeightLog/Progress model not found"
    except Exception as e:
        out["weight_logs_error"] = str(e)

    try:
        if ExerciseLog:
            rows = ExerciseLog.query.filter_by(user_id=user.id).order_by(getattr(ExerciseLog, 'id').desc()).limit(20).all()
            out["exercise_logs_recent"] = summarize(rows, ['id', 'name', 'exercise_name', 'reps', 'notes', 'date', 'log_date'])
        else:
            out["exercise_logs_recent"] = "ExerciseLog model not found"
    except Exception as e:
        out["exercise_logs_error"] = str(e)

    return jsonify(out)
# ...existing code...