import os

from datetime import datetime, timedelta
import calendar as _calendar
import math

from flask import Blueprint, render_template, flash, redirect, url_for, request, abort, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import (
    User,
    UserFoodLog,
    Progress,
    AssignedTemplate,
    ExerciseTemplate,
    WorkoutSession,
    WorkoutSet,
    Food,
    FoodMeasure,
    TrainerMeal,
    TrainerMealIngredient,
    Message,
)
from app.services.nutrition import (
    convert_to_grams,
    serialize_meal,
    group_meals_by_slot,
    MEAL_SLOT_LABELS,
)
from app.routes.member import build_member_summary_context
from sqlalchemy import or_, func
import pytz

trainer_bp = Blueprint('trainer', __name__, url_prefix='/trainer')

@trainer_bp.route('/dashboard-trainer')
@login_required
def dashboard_trainer():
    if current_user.role != 'trainer':
        flash("Access denied.", "danger")
        return redirect(url_for('main.home'))

    est = pytz.timezone("America/New_York")
    today = datetime.now(est).date()
    members = (
        User.query
        .filter_by(trainer_id=current_user.id, role='member')
        .order_by(User.first_name.asc(), User.last_name.asc())
        .all()
    )

    clients = []
    for member in members:
        totals = {key: 0.0 for key in ("calories", "protein", "carbs", "fats")}
        logs = UserFoodLog.query.filter_by(user_id=member.id, log_date=today).all()
        for log in logs:
            scaled = log.scaled
            for key in totals:
                totals[key] += scaled.get(key, 0)

        latest_progress = (
            Progress.query
            .filter_by(user_id=member.id)
            .order_by(Progress.date.desc())
            .first()
        )

        weight = None
        if latest_progress and latest_progress.weight is not None:
            weight = round(latest_progress.weight, 1)

        clients.append({
            "record": member,
            "macros": {k: round(v, 1) for k, v in totals.items()},
            "weight": weight,
            "age": getattr(member, "age", None),
            "gender": getattr(member, "gender", None),
        })

    return render_template(
        'dashboard-trainer.html',
        trainer=current_user,
        clients=clients,
        today=today
    )


def _format_height(height_cm):
    if not height_cm:
        return None, None
    try:
        total_inches = float(height_cm) / 2.54
        feet = int(total_inches // 12)
        inches = round(total_inches - (feet * 12), 1)
        if inches == 12:
            feet += 1
            inches = 0
        return feet, inches
    except (TypeError, ValueError):
        return None, None


def _get_trainer_client(member_id: int) -> User:
    if current_user.role != 'trainer':
        abort(403)
    client = User.query.filter_by(
        id=member_id,
        trainer_id=current_user.id,
        role='member'
    ).first()
    if not client:
        abort(404)
    return client


@trainer_bp.route('/clients/<int:member_id>/remove', methods=['POST'])
@login_required
def remove_client(member_id):
    if current_user.role != 'trainer':
        flash("Access denied.", "danger")
        return redirect(url_for('main.home'))

    client = _get_trainer_client(member_id)
    client_name = f"{client.first_name} {client.last_name}"
    client.trainer_id = None
    db.session.commit()
    flash(f"Removed {client_name} from your client list.", "success")
    return redirect(url_for('trainer.dashboard_trainer'))


@trainer_bp.route('/clients/<int:member_id>', methods=['GET', 'POST'])
@login_required
def client_detail(member_id):
    if current_user.role != 'trainer':
        flash("Access denied.", "danger")
        return redirect(url_for('main.home'))

    client = User.query.filter_by(
        id=member_id,
        trainer_id=current_user.id,
        role='member'
    ).first()

    if not client:
        flash("Client not found.", "danger")
        return redirect(url_for('trainer.dashboard_trainer'))

    redirect_view = request.args.get('view')

    if request.method == 'POST':
        action = request.form.get('action', 'update_calories')
        redirect_view = request.form.get('redirect_view') or redirect_view

        if action == 'update_macros':
            field_mapping = {
                'custom_calorie_target': ('custom_calorie_target', "calorie target"),
                'custom_protein_target': ('custom_protein_target_g', "protein target"),
                'custom_carb_target': ('custom_carb_target_g', "carb target"),
                'custom_fat_target': ('custom_fat_target_g', "fat target"),
            }
            updated_macros = False
            for form_key, (attr_name, label) in field_mapping.items():
                raw_value = request.form.get(form_key)
                if raw_value is None:
                    continue
                value = raw_value.strip()
                if value == '':
                    if getattr(client, attr_name) is not None:
                        setattr(client, attr_name, None)
                        updated_macros = True
                else:
                    try:
                        setattr(client, attr_name, float(value))
                        updated_macros = True
                    except ValueError:
                        flash(f"Invalid {label}.", "warning")

            mode_changed = client.macro_target_mode != 'grams'
            client.macro_target_mode = 'grams'
            if updated_macros or mode_changed:
                db.session.commit()
                flash("Custom macro targets updated.", "success")
            else:
                flash("No macro changes detected.", "info")

            if redirect_view:
                return redirect(url_for('trainer.client_detail', member_id=client.id, view=redirect_view))
            return redirect(url_for('trainer.client_detail', member_id=client.id))
        elif action == 'update_macro_percent':
            ratio_mapping = [
                ('macro_ratio_protein', 'protein_percent', "protein percentage"),
                ('macro_ratio_carbs', 'carb_percent', "carb percentage"),
                ('macro_ratio_fats', 'fat_percent', "fat percentage"),
            ]
            ratio_updates = {}
            ratio_changed = False
            invalid_input = False
            for attr_name, form_key, label in ratio_mapping:
                raw_value = request.form.get(form_key, '')
                value = raw_value.strip()
                if value == '':
                    new_value = None
                else:
                    try:
                        pct_value = float(value)
                        if pct_value < 0 or pct_value > 100:
                            raise ValueError
                    except ValueError:
                        flash(f"Invalid {label}.", "warning")
                        invalid_input = True
                        break
                    new_value = pct_value / 100.0
                ratio_updates[attr_name] = new_value
            if invalid_input:
                if redirect_view:
                    return redirect(url_for('trainer.client_detail', member_id=client.id, view=redirect_view))
                return redirect(url_for('trainer.client_detail', member_id=client.id))

            for attr_name, new_value in ratio_updates.items():
                if getattr(client, attr_name) != new_value:
                    ratio_changed = True
                    setattr(client, attr_name, new_value)

            mode_changed = client.macro_target_mode != 'percent'
            client.macro_target_mode = 'percent'
            if ratio_changed or mode_changed:
                db.session.commit()
                flash("Macro percentages updated.", "success")
            else:
                flash("No macro percentage changes detected.", "info")

            if redirect_view:
                return redirect(url_for('trainer.client_detail', member_id=client.id, view=redirect_view))
            return redirect(url_for('trainer.client_detail', member_id=client.id))

        maintenance_raw = request.form.get('maintenance_calories')
        goal_raw = request.form.get('calorie_goal')

        updated = False

        if maintenance_raw is not None:
            maintenance_val = maintenance_raw.strip()
            if maintenance_val == '':
                client.maintenance_calories = None
                updated = True
            else:
                try:
                    client.maintenance_calories = float(maintenance_val)
                    updated = True
                except ValueError:
                    flash("Invalid maintenance calories value.", "warning")

        if goal_raw is not None:
            goal_val = goal_raw.strip()
            if goal_val == '':
                client.calorie_goal = None
                updated = True
            else:
                try:
                    client.calorie_goal = float(goal_val)
                    updated = True
                except ValueError:
                    flash("Invalid calorie goal value.", "warning")

        if updated:
            db.session.commit()
            flash("Calorie targets updated.", "success")

        if redirect_view:
            return redirect(url_for('trainer.client_detail', member_id=client.id, view=redirect_view))
        return redirect(url_for('trainer.client_detail', member_id=client.id))

    est = pytz.timezone("America/New_York")
    today = datetime.now(est).date()
    latest_progress = (
        Progress.query
        .filter_by(user_id=client.id)
        .order_by(Progress.date.desc())
        .first()
    )
    latest_weight = float(latest_progress.weight) if latest_progress and latest_progress.weight is not None else None

    height_feet, height_inches = _format_height(client.height_cm)

    assigned_templates = (
        AssignedTemplate.query
        .filter_by(trainer_id=current_user.id, member_id=client.id)
        .order_by(AssignedTemplate.assigned_at.desc())
        .all()
    )

    recent_sessions = (
        WorkoutSession.query
        .filter_by(user_id=client.id)
        .order_by(WorkoutSession.started_at.desc())
        .limit(5)
        .all()
    )

    recent_weights = (
        Progress.query
        .filter_by(user_id=client.id)
        .order_by(Progress.date.desc())
        .limit(5)
        .all()
    )

    view = request.args.get('view')
    cal_year = request.args.get('year', type=int)
    cal_month = request.args.get('month', type=int)
    sel_day = request.args.get('day')

    calendar_weeks = None
    selected_date = None
    selected_weight = None
    selected_workouts = []

    progress_entries = (
        Progress.query
        .filter_by(user_id=client.id)
        .order_by(Progress.date.asc())
        .all()
    )

    weight_map = {}
    for entry in progress_entries:
        dt = entry.date
        if isinstance(dt, datetime):
            day = dt.date()
        else:
            day = dt
        try:
            weight_map[day] = float(entry.weight) if entry.weight is not None else None
        except (TypeError, ValueError):
            weight_map[day] = None

    workout_sessions = (
        WorkoutSession.query
        .filter_by(user_id=client.id)
        .order_by(WorkoutSession.started_at.desc())
        .all()
    )

    workout_map = {}
    for sess in workout_sessions:
        dt = sess.completed_at or sess.started_at
        if not dt:
            continue
        try:
            day = dt.date()
        except Exception:
            continue
        workout_map.setdefault(day, []).append(sess)

    def _format_time(dt_obj):
        if not dt_obj:
            return ''
        try:
            return dt_obj.strftime('%H:%M')
        except Exception:
            return ''

    if view == 'calendar':
        if not cal_year or not cal_month:
            cal_year = today.year
            cal_month = today.month

        try:
            selected_date = datetime.strptime(sel_day, "%Y-%m-%d").date() if sel_day else today
        except Exception:
            selected_date = today

        cal = _calendar.Calendar(firstweekday=6)
        calendar_weeks = []
        for week in cal.monthdatescalendar(cal_year, cal_month):
            week_data = []
            for d in week:
                if d.month != cal_month:
                    week_data.append({'iso': '', 'day': '', 'in_month': False, 'data': None})
                    continue

                workouts_for_day = [
                    {
                        'id': sess.id,
                        'summary': sess.summary,
                        'time': _format_time(sess.completed_at or sess.started_at),
                        'template': sess.template.name if sess.template else None,
                    }
                    for sess in workout_map.get(d, [])
                ]

                week_data.append({
                    'iso': d.strftime('%Y-%m-%d'),
                    'day': d.day,
                    'in_month': True,
                    'data': {
                        'weight': weight_map.get(d),
                        'workouts': workouts_for_day or None,
                    }
                })
            calendar_weeks.append(week_data)

        selected_weight = weight_map.get(selected_date)

        sessions_for_day = workout_map.get(selected_date, [])
        for sess in sessions_for_day:
            workout_sets = (
                WorkoutSet.query
                .filter_by(session_id=sess.id)
                .order_by(WorkoutSet.exercise_name.asc(), WorkoutSet.set_number.asc())
                .all()
            )
            selected_workouts.append({
                'session': sess,
                'time': _format_time(sess.completed_at or sess.started_at),
                'summary': sess.summary,
                'sets': workout_sets,
            })

    trainer_meals = (
        TrainerMeal.query
        .filter(TrainerMeal.trainer_id == current_user.id)
        .filter(
            or_(
                TrainerMeal.member_id == client.id,
                TrainerMeal.member_id.is_(None)
            )
        )
        .order_by(TrainerMeal.meal_slot.asc(), TrainerMeal.name.asc())
        .all()
    )
    meals_by_slot = group_meals_by_slot(trainer_meals) if trainer_meals else {slot: [] for slot in MEAL_SLOT_LABELS}
    macro_targets = {
        "calories": client.custom_calorie_target,
        "protein": client.custom_protein_target_g,
        "carbs": client.custom_carb_target_g,
        "fats": client.custom_fat_target_g,
    }

    return render_template(
        'client-detail.html',
        trainer=current_user,
        client=client,
        view=view,
        today=today,
        latest_weight=latest_weight,
        height_feet=height_feet,
        height_inches=height_inches,
        assigned_templates=assigned_templates,
        recent_sessions=recent_sessions,
        recent_weights=recent_weights,
        calendar_weeks=calendar_weeks,
        cal_year=cal_year,
        cal_month=cal_month,
        selected_date=selected_date,
        selected_weight=selected_weight,
        selected_workouts=selected_workouts,
        meals_by_slot=meals_by_slot,
        meal_slot_labels=MEAL_SLOT_LABELS,
        macro_targets=macro_targets,
    )


def _build_ingredient_models(food_ids, quantities, units, notes, positions):
    ingredients = []
    for idx, food_id_raw in enumerate(food_ids):
        if not food_id_raw:
            continue
        try:
            food_id = int(food_id_raw)
        except (TypeError, ValueError):
            continue

        if not Food.query.get(food_id):
            flash(f"Food ID {food_id} not found. Ingredient skipped.", "warning")
            continue

        quantity_raw = quantities[idx] if idx < len(quantities) else ""
        if not quantity_raw or not quantity_raw.strip():
            flash("Each ingredient requires a quantity.", "warning")
            continue

        try:
            quantity = float(quantity_raw)
        except (TypeError, ValueError):
            flash("Invalid ingredient quantity provided.", "warning")
            continue

        if quantity <= 0:
            flash("Ingredient quantity must be greater than zero.", "warning")
            continue

        unit = units[idx].strip().lower() if idx < len(units) and units[idx] else "g"
        grams, volume_ml = convert_to_grams(food_id, quantity, unit)
        position_raw = positions[idx] if idx < len(positions) else ""
        try:
            position = int(position_raw)
        except (TypeError, ValueError):
            position = idx

        ingredient = TrainerMealIngredient(
            food_id=food_id,
            quantity_value=quantity,
            quantity_unit=unit or "g",
            quantity_grams=grams,
            volume_ml=volume_ml,
            position=position,
            notes=notes[idx].strip() if idx < len(notes) and notes[idx] else None,
        )
        ingredients.append(ingredient)
    return ingredients


@trainer_bp.route('/meals/new', methods=['GET', 'POST'])
@trainer_bp.route('/clients/<int:member_id>/meals/new', methods=['GET', 'POST'])
@login_required
def create_meal(member_id=None):
    client = _get_trainer_client(member_id) if member_id else None

    if request.method == 'POST':
        name = (request.form.get('meal_name') or '').strip()
        meal_slot = (request.form.get('meal_slot') or 'meal1').strip().lower()
        description = (request.form.get('description') or '').strip()

        if not name:
            flash("Meal name is required.", "warning")
            if member_id:
                return redirect(url_for('trainer.create_meal', member_id=member_id))
            return redirect(url_for('trainer.create_meal'))

        food_ids = request.form.getlist('ingredient_food_id[]')
        quantities = request.form.getlist('ingredient_quantity[]')
        units = request.form.getlist('ingredient_unit[]')
        notes = request.form.getlist('ingredient_notes[]')
        positions = request.form.getlist('ingredient_position[]')

        ingredients = _build_ingredient_models(food_ids, quantities, units, notes, positions)

        if not ingredients:
            flash("Please add at least one ingredient.", "warning")
            if member_id:
                return redirect(url_for('trainer.create_meal', member_id=member_id))
            return redirect(url_for('trainer.create_meal'))

        meal = TrainerMeal(
            trainer_id=current_user.id,
            member_id=client.id if client else None,
            name=name,
            description=description or None,
            meal_slot=meal_slot if meal_slot in MEAL_SLOT_LABELS else 'meal1',
        )
        for idx, ingredient in enumerate(sorted(ingredients, key=lambda ing: ing.position)):
            ingredient.position = idx
            meal.ingredients.append(ingredient)

        db.session.add(meal)
        db.session.commit()

        flash(f"Meal '{meal.name}' created.", "success")
        if member_id:
            return redirect(url_for('trainer.client_detail', member_id=member_id))
        return redirect(url_for('trainer.dashboard_trainer'))

    meal_data = {
        "name": "",
        "description": "",
        "slot": request.args.get('slot', 'meal1'),
        "ingredients": [],
    }
    return render_template(
        'trainer-meal-form.html',
        trainer=current_user,
        client=client,
        meal=None,
        meal_data=meal_data,
        meal_slot_labels=MEAL_SLOT_LABELS,
    )


@trainer_bp.route('/meals/<int:meal_id>/edit', methods=['GET', 'POST'])
@trainer_bp.route('/clients/<int:member_id>/meals/<int:meal_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_meal(meal_id, member_id=None):
    client = _get_trainer_client(member_id) if member_id else None
    meal = (
        TrainerMeal.query
        .filter_by(id=meal_id, trainer_id=current_user.id)
        .first_or_404()
    )
    if member_id and meal.member_id not in (None, client.id):
        abort(404)

    if request.method == 'POST':
        name = (request.form.get('meal_name') or '').strip()
        meal_slot = (request.form.get('meal_slot') or 'meal1').strip().lower()
        description = (request.form.get('description') or '').strip()

        if not name:
            flash("Meal name is required.", "warning")
            if member_id:
                return redirect(url_for('trainer.edit_meal', member_id=member_id, meal_id=meal_id))
            return redirect(url_for('trainer.edit_meal', meal_id=meal_id))

        food_ids = request.form.getlist('ingredient_food_id[]')
        quantities = request.form.getlist('ingredient_quantity[]')
        units = request.form.getlist('ingredient_unit[]')
        notes = request.form.getlist('ingredient_notes[]')
        positions = request.form.getlist('ingredient_position[]')

        ingredients = _build_ingredient_models(food_ids, quantities, units, notes, positions)

        if not ingredients:
            flash("Please include at least one ingredient.", "warning")
            return redirect(url_for('trainer.edit_meal', member_id=member_id, meal_id=meal_id))

        meal.name = name
        meal.description = description or None
        meal.meal_slot = meal_slot if meal_slot in MEAL_SLOT_LABELS else meal.meal_slot

        meal.ingredients.clear()
        for idx, ingredient in enumerate(sorted(ingredients, key=lambda ing: ing.position)):
            ingredient.position = idx
            meal.ingredients.append(ingredient)

        db.session.commit()
        flash(f"Meal '{meal.name}' updated.", "success")
        if member_id:
            return redirect(url_for('trainer.client_detail', member_id=member_id))
        return redirect(url_for('trainer.dashboard_trainer'))

    meal_data = serialize_meal(meal)
    return render_template(
        'trainer-meal-form.html',
        trainer=current_user,
        client=client,
        meal=meal,
        meal_data=meal_data,
        meal_slot_labels=MEAL_SLOT_LABELS,
    )


@trainer_bp.route('/meals/<int:meal_id>/delete', methods=['POST'])
@trainer_bp.route('/clients/<int:member_id>/meals/<int:meal_id>/delete', methods=['POST'])
@login_required
def delete_meal(meal_id, member_id=None):
    client = _get_trainer_client(member_id) if member_id else None
    meal = TrainerMeal.query.filter_by(
        id=meal_id,
        trainer_id=current_user.id
    ).first()

    if not meal:
        flash("Meal not found.", "warning")
        if member_id:
            return redirect(url_for('trainer.client_detail', member_id=member_id))
        return redirect(url_for('trainer.dashboard_trainer'))

    if client and meal.member_id not in (None, client.id):
        flash("Meal not found.", "warning")
        return redirect(url_for('trainer.client_detail', member_id=member_id))

    db.session.delete(meal)
    db.session.commit()
    flash("Meal removed.", "success")
    if member_id:
        return redirect(url_for('trainer.client_detail', member_id=member_id))
    return redirect(url_for('trainer.dashboard_trainer'))


@trainer_bp.route('/meals/custom-food', methods=['POST'])
@login_required
def create_custom_food():
    if current_user.role != 'trainer':
        return jsonify({"status": "error", "message": "Access denied."}), 403

    payload = request.get_json(silent=True) or {}
    name = (payload.get('name') or '').strip()
    calories = payload.get('calories')
    protein = payload.get('protein')
    carbs = payload.get('carbs')
    fats = payload.get('fats')
    quantity = payload.get('quantity')
    unit = (payload.get('unit') or 'g').strip().lower()
    grams = payload.get('grams')
    volume_ml = payload.get('volume_ml')

    if not name:
        return jsonify({"status": "error", "message": "Name is required."}), 400

    def _to_float(value):
        if value in (None, ''):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    calories_val = _to_float(calories)
    protein_val = _to_float(protein)
    carbs_val = _to_float(carbs)
    fats_val = _to_float(fats)
    quantity_val = _to_float(quantity) or 1.0
    grams_val = _to_float(grams)
    volume_val = _to_float(volume_ml)

    if grams_val is None and unit not in ("g", ""):
        return jsonify({"status": "error", "message": "Please provide gram weight for custom unit."}), 400

    food = Food(
        name=name,
        calories=calories_val,
        protein_g=protein_val,
        carbs_g=carbs_val,
        fats_g=fats_val,
        source_id=None,
        serving_size=grams_val if grams_val else 100,
        serving_unit=unit if unit else "g",
        grams_per_unit=grams_val if grams_val else 100
    )
    db.session.add(food)
    db.session.commit()

    if unit:
        measure = FoodMeasure(
            food_id=food.id,
            measure_name=unit,
            grams=(grams_val or 1.0) / quantity_val
        )
        db.session.add(measure)
        db.session.commit()

    return jsonify({
        "status": "success",
        "food": {
            "id": food.id,
            "name": food.name,
            "calories": food.calories or 0,
            "protein_g": food.protein_g or 0,
            "carbs_g": food.carbs_g or 0,
            "fats_g": food.fats_g or 0
        }
    })

@trainer_bp.route('/clients/<int:member_id>/summary-view')
@login_required
def client_summary_view(member_id):
    """Render an interactive summary dashboard for a specific client (weekly + monthly)."""
    if current_user.role != 'trainer':
        flash("Access denied.", "danger")
        return redirect(url_for('trainer.dashboard_trainer'))

    client = _get_trainer_client(member_id)
    macro_week_param = request.args.get("macro_week", type=int)
    context = build_member_summary_context(client, macro_week_param)
    macro_week_prev = context.get("macro_week_prev")
    macro_week_next = context.get("macro_week_next")
    context.update({
        "summary_role": "trainer",
        "summary_nav": "trainer",
        "macro_prev_url": url_for('trainer.client_summary_view', member_id=client.id, macro_week=macro_week_prev) if macro_week_prev is not None else None,
        "macro_next_url": url_for('trainer.client_summary_view', member_id=client.id, macro_week=macro_week_next) if macro_week_next is not None else None,
    })
    return render_template("member-summary.html", **context)


@trainer_bp.route('/send-message/<int:client_id>', methods=['GET', 'POST'])
@login_required
def send_message(client_id: int):
    if current_user.role != 'trainer':
        flash("Access denied.", "danger")
        return redirect(url_for('main.home'))

    client = _get_trainer_client(client_id)

    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        if not content:
            flash("Message cannot be empty.", "warning")
            return redirect(url_for('trainer.send_message', client_id=client_id))

        message = Message(
            trainer_id=current_user.id,
            client_id=client.id,
            content=content,
        )
        db.session.add(message)
        db.session.commit()

        flash("Message sent successfully.", "success")
        return redirect(url_for('trainer.dashboard_trainer'))

    return render_template(
        'trainer_send_message.html',
        trainer=current_user,
        client=client,
    )

        
