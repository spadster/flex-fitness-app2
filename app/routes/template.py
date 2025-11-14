from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from app.models import (
    User,
    ExerciseTemplate,
    TemplateExercise,
    ExerciseCatalog,
    AssignedTemplate,
    WorkoutSession,
    WorkoutSet,
)
from datetime import datetime
import json
from sqlalchemy import or_


template_bp = Blueprint('template', __name__, url_prefix='/templates')


def _search_exercises(term):
    if not term:
        return []

    like_term = f"%{term}%"
    rows = (
        ExerciseCatalog.query
        .filter(
            or_(
                ExerciseCatalog.name.ilike(like_term),
                ExerciseCatalog.primary_muscles.ilike(like_term),
                ExerciseCatalog.secondary_muscles.ilike(like_term),
                ExerciseCatalog.equipment.ilike(like_term),
                ExerciseCatalog.category.ilike(like_term),
            )
        )
        .order_by(ExerciseCatalog.name.asc())
        .limit(25)
        .all()
    )

    results = []
    for row in rows:
        muscle = row.primary_muscles or row.secondary_muscles or (row.category.title() if row.category else None)
        results.append({
            "name": row.name,
            "muscle": muscle,
            "equipment": row.equipment,
        })
    return results


def _human_duration(started_at, completed_at):
    if not started_at:
        return "--"
    end_time = completed_at or datetime.utcnow()
    try:
        diff = end_time - started_at
    except Exception:
        return "--"
    total_seconds = max(int(diff.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


@template_bp.route('/api/search')
@login_required
def search_exercises_api():
    query = (request.args.get('q') or '').strip()
    if not query:
        return jsonify({"results": []})

    matches = _search_exercises(query)
    return jsonify({"results": matches or []})


@template_bp.route('/', methods=['GET', 'POST'])
@login_required
def list_templates():
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        description = (request.form.get('description') or '').strip()
        if not name:
            flash('Template name is required.', 'warning')
            return redirect(url_for('template.list_templates'))

        tpl = ExerciseTemplate(owner_id=current_user.id, name=name, description=description)
        db.session.add(tpl)
        db.session.commit()
        flash('Template created.', 'success')
        return redirect(url_for('template.view_template', template_id=tpl.id))

    my_templates = ExerciseTemplate.query.filter_by(owner_id=current_user.id).order_by(ExerciseTemplate.created_at.desc()).all()

    assigned_to_me = []
    if current_user.role == 'member':
        # templates assigned to this member
        assigned_to_me = (
            AssignedTemplate.query
            .filter_by(member_id=current_user.id)
            .all()
        )
    elif current_user.role == 'trainer':
        # templates this trainer assigned to clients, show summary
        assigned_to_me = (
            AssignedTemplate.query
            .filter_by(trainer_id=current_user.id)
            .all()
        )

    return render_template('exercise-templates.html', my_templates=my_templates, assignments=assigned_to_me, user=current_user)


@template_bp.route('/<int:template_id>', methods=['GET'])
@login_required
def view_template(template_id):
    tpl = ExerciseTemplate.query.get_or_404(template_id)
    if tpl.owner_id != current_user.id:
        flash('You do not have access to this template.', 'danger')
        return redirect(url_for('template.list_templates'))

    return render_template('template-detail.html', template=tpl)


@template_bp.route('/<int:template_id>/add-exercise', methods=['POST'])
@login_required
def add_exercise(template_id):
    tpl = ExerciseTemplate.query.get_or_404(template_id)
    if tpl.owner_id != current_user.id:
        flash('You do not have access to modify this template.', 'danger')
        return redirect(url_for('template.list_templates'))

    payload = request.get_json(silent=True)
    if payload:
        name = (payload.get('exercise_name') or '').strip()
        sets = payload.get('sets')
        reps = payload.get('reps')
        muscle = payload.get('muscle')
        equipment = payload.get('equipment')
    else:
        name = (request.form.get('exercise_name') or '').strip()
        sets = request.form.get('sets')
        reps = request.form.get('reps')
        muscle = request.form.get('muscle')
        equipment = request.form.get('equipment')

    if not name:
        flash('Exercise name is required.', 'warning')
        return redirect(url_for('template.view_template', template_id=template_id))

    try:
        sets_val = int(sets) if sets not in (None, "") else None
        reps_val = int(reps) if reps not in (None, "") else None
    except (TypeError, ValueError):
        if payload:
            return jsonify({"status": "error", "message": "Invalid sets or reps."}), 400
        flash('Invalid sets or reps.', 'warning')
        return redirect(url_for('template.view_template', template_id=template_id))

    ex = TemplateExercise(
        template_id=tpl.id,
        exercise_name=name,
        muscle=muscle,
        equipment=equipment,
        default_sets=sets_val,
        default_reps=reps_val,
    )
    db.session.add(ex)
    db.session.commit()

    if payload:
        return jsonify({
            "status": "success",
            "exercise": {
                "id": ex.id,
                "name": ex.exercise_name,
                "sets": ex.default_sets,
                "reps": ex.default_reps,
                "muscle": ex.muscle,
                "equipment": ex.equipment,
            }
        }), 201

    flash('Exercise added to template.', 'success')
    return redirect(url_for('template.view_template', template_id=template_id))


@template_bp.route('/<int:template_id>/assign', methods=['GET', 'POST'])
@login_required
def assign_template(template_id):
    tpl = ExerciseTemplate.query.get_or_404(template_id)
    if current_user.role != 'trainer' or tpl.owner_id != current_user.id:
        flash('Only trainers can assign templates.', 'danger')
        return redirect(url_for('template.list_templates'))

    if request.method == 'POST':
        member_ids = request.form.getlist('member_ids')
        if not member_ids:
            flash('Select at least one client.', 'warning')
            return redirect(url_for('template.assign_template', template_id=template_id))

        count = 0
        for mid in member_ids:
            try:
                mid_int = int(mid)
            except ValueError:
                continue
            member = User.query.filter_by(id=mid_int, trainer_id=current_user.id, role='member').first()
            if not member:
                continue
            # Avoid duplicate assignment
            exists = AssignedTemplate.query.filter_by(template_id=tpl.id, trainer_id=current_user.id, member_id=member.id).first()
            if exists:
                continue
            db.session.add(AssignedTemplate(template_id=tpl.id, trainer_id=current_user.id, member_id=member.id))
            count += 1
        db.session.commit()
        flash(f'Assigned to {count} client(s).', 'success')
        return redirect(url_for('template.assign_template', template_id=template_id))

    clients = User.query.filter_by(trainer_id=current_user.id, role='member').order_by(User.first_name.asc(), User.last_name.asc()).all()
    current_assignments = AssignedTemplate.query.filter_by(template_id=tpl.id, trainer_id=current_user.id).all()
    assigned_ids = {a.member_id for a in current_assignments}
    return render_template('assign-template.html', template=tpl, clients=clients, assigned_ids=assigned_ids)


@template_bp.route('/workouts/start/<int:template_id>', methods=['GET', 'POST'])
@login_required
def start_workout(template_id):
    tpl = ExerciseTemplate.query.get_or_404(template_id)
    # Members can use assigned templates or their own; trainers can use any they own
    if tpl.owner_id != current_user.id and current_user.role == 'member':
        assigned = AssignedTemplate.query.filter_by(template_id=tpl.id, member_id=current_user.id).first()
        if not assigned:
            flash('You do not have access to this template.', 'danger')
            return redirect(url_for('template.list_templates'))

    for_user_id_value = request.form.get('for_user_id') if request.method == 'POST' else request.args.get('for_user_id')
    target_user = current_user
    redirect_kwargs = {'template_id': template_id}

    if for_user_id_value not in (None, ''):
        try:
            for_user_id = int(for_user_id_value)
        except (TypeError, ValueError):
            for_user_id = None
        if for_user_id and for_user_id != current_user.id:
            if current_user.role != 'trainer':
                flash('You do not have access to that client.', 'danger')
                return redirect(url_for('template.list_templates'))
            target_user = User.query.filter_by(id=for_user_id, trainer_id=current_user.id, role='member').first()
            if not target_user:
                flash('Client not found.', 'danger')
                return redirect(url_for('template.list_templates'))
            assignment = AssignedTemplate.query.filter_by(template_id=tpl.id, trainer_id=current_user.id, member_id=target_user.id).first()
            if not assignment and tpl.owner_id != current_user.id:
                flash('Template is not assigned to this client.', 'danger')
                return redirect(url_for('trainer.client_detail', member_id=target_user.id))
            redirect_kwargs['for_user_id'] = target_user.id
    else:
        for_user_id = None

    if request.method == 'POST':
        payload_raw = request.form.get('workout_payload')
        try:
            payload = json.loads(payload_raw) if payload_raw else []
        except json.JSONDecodeError:
            flash('Invalid workout data received.', 'danger')
            return redirect(url_for('template.start_workout', **redirect_kwargs))

        if not isinstance(payload, list) or not payload:
            flash('Please log at least one exercise.', 'warning')
            return redirect(url_for('template.start_workout', **redirect_kwargs))

        started_at_raw = request.form.get('started_at')
        try:
            started_at = datetime.fromisoformat(started_at_raw) if started_at_raw else datetime.utcnow()
        except ValueError:
            started_at = datetime.utcnow()

        session = WorkoutSession(user_id=target_user.id, template_id=tpl.id, started_at=started_at)
        db.session.add(session)
        db.session.flush()

        total_sets = 0
        summary_parts = []

        for exercise in payload:
            name = (exercise.get('name') or '').strip()
            if not name:
                continue

            template_ex_id = exercise.get('templateExerciseId')
            try:
                template_ex_id = int(template_ex_id) if template_ex_id not in (None, '') else None
            except (TypeError, ValueError):
                template_ex_id = None

            sets_payload = exercise.get('sets') or []
            clean_sets = []
            for idx, set_obj in enumerate(sets_payload, start=1):
                reps_raw = set_obj.get('reps')
                weight_raw = set_obj.get('weight')

                reps_val = None
                weight_val = None

                if reps_raw not in (None, ''):
                    try:
                        reps_val = int(reps_raw)
                    except (TypeError, ValueError):
                        reps_val = None

                if weight_raw not in (None, ''):
                    try:
                        weight_val = float(weight_raw)
                    except (TypeError, ValueError):
                        weight_val = None

                if reps_val is None and weight_val is None:
                    continue

                clean_sets.append({"reps": reps_val, "weight": weight_val})
                db.session.add(WorkoutSet(
                    session_id=session.id,
                    template_exercise_id=template_ex_id,
                    exercise_name=name,
                    set_number=len(clean_sets),
                    reps=reps_val if reps_val is not None else 0,
                    weight=weight_val
                ))

            if not clean_sets:
                continue

            total_sets += len(clean_sets)
            first = clean_sets[0]
            rep_part = f"{first['reps']}" if first['reps'] is not None else '—'
            weight_part = ''
            if first['weight'] is not None:
                weight_part = f" @ {round(first['weight'], 1)} lbs"
            summary_parts.append(f"{name}: {len(clean_sets)} set(s) × {rep_part}{weight_part}")

        if total_sets == 0:
            db.session.rollback()
            flash('No sets were logged. Please add at least one set.', 'warning')
            return redirect(url_for('template.start_workout', **redirect_kwargs))

        session.completed_at = datetime.utcnow()
        summary_text = '; '.join(summary_parts)
        if len(summary_text) > 250:
            summary_text = summary_text[:247] + '...'
        session.summary = summary_text

        db.session.commit()
        flash('Workout logged.', 'success')
        if target_user.id != current_user.id:
            return redirect(url_for('trainer.client_detail', member_id=target_user.id, view='calendar'))
        return redirect(url_for('template.view_session', session_id=session.id))

    # Build initial data using latest session as defaults
    last_session = (
        WorkoutSession.query
        .filter_by(user_id=target_user.id, template_id=tpl.id)
        .order_by(WorkoutSession.completed_at.desc().nullslast(), WorkoutSession.started_at.desc())
        .first()
    )

    last_sets_map = {}
    if last_session:
        previous_sets = (
            WorkoutSet.query
            .filter_by(session_id=last_session.id)
            .order_by(WorkoutSet.exercise_name.asc(), WorkoutSet.set_number.asc())
            .all()
        )
        for s in previous_sets:
            if s.template_exercise_id:
                key = f"tpl:{s.template_exercise_id}"
            else:
                key = f"custom:{s.exercise_name.lower()}"
            entry = last_sets_map.setdefault(key, {
                "templateExerciseId": s.template_exercise_id,
                "name": s.exercise_name,
                "sets": []
            })
            entry["sets"].append({
                "reps": s.reps,
                "weight": s.weight
            })

    initial_payload = []
    for ex in tpl.exercises:
        key = f"tpl:{ex.id}"
        prev = last_sets_map.pop(key, None)
        sets_payload = prev["sets"] if prev else []
        if not sets_payload:
            sets_payload = [{"reps": ex.default_reps, "weight": None}]

        initial_payload.append({
            "templateExerciseId": ex.id,
            "name": ex.exercise_name,
            "muscle": ex.muscle,
            "equipment": ex.equipment,
            "sets": sets_payload
        })

    # Include custom exercises from last session
    for key, data in last_sets_map.items():
        initial_payload.append({
            "templateExerciseId": data.get('templateExerciseId'),
            "name": data.get('name'),
            "muscle": None,
            "equipment": None,
            "sets": data.get('sets') or [{"reps": None, "weight": None}]
        })

    for item in initial_payload:
        if not item.get('sets'):
            item['sets'] = [{"reps": None, "weight": None}]

    start_time_obj = datetime.utcnow()
    logging_for_client = (target_user.id != current_user.id)

    return render_template(
        'start-workout.html',
        template=tpl,
        initial_data=initial_payload,
        start_time_iso=start_time_obj.isoformat(),
        start_time_display=start_time_obj.strftime('%Y-%m-%d %H:%M'),
        target_user=target_user,
        logging_for_client=logging_for_client
    )


@template_bp.route('/workouts/session/<int:session_id>')
@login_required
def view_session(session_id):
    session = WorkoutSession.query.get_or_404(session_id)
    if session.user_id != current_user.id and current_user.role != 'trainer':
        flash('You do not have access to this session.', 'danger')
        return redirect(url_for('template.list_templates'))

    sets = (
        WorkoutSet.query
        .filter_by(session_id=session.id)
        .order_by(WorkoutSet.exercise_name.asc(), WorkoutSet.set_number.asc())
        .all()
    )
    exercise_map = {}
    total_volume = 0
    for s in sets:
        name = s.exercise_name or "Exercise"
        entry = exercise_map.setdefault(name, {"sets": []})
        entry["sets"].append(s)
        reps = s.reps or 0
        weight_val = s.weight if s.weight is not None else 0
        total_volume += weight_val * reps

    exercise_details = []
    for name, data in sorted(exercise_map.items()):
        best_weight = None
        best_reps = 0
        formatted_sets = []
        for idx, s in enumerate(data["sets"], start=1):
            reps = s.reps or 0
            weight_val = s.weight
            formatted_sets.append({
                "index": idx,
                "reps": reps,
                "weight": round(weight_val, 1) if weight_val is not None else None,
            })
            compare_weight = weight_val if weight_val is not None else 0
            current_best = best_weight if best_weight is not None else 0
            should_replace = False
            if best_weight is None or compare_weight > current_best:
                should_replace = True
            elif compare_weight == current_best and reps > best_reps:
                should_replace = True
            if should_replace:
                best_weight = round(weight_val, 1) if weight_val is not None else None
                best_reps = reps

        exercise_details.append({
            "name": name,
            "total_sets": len(data["sets"]),
            "best_weight": best_weight,
            "best_reps": best_reps,
            "sets": formatted_sets,
        })

    duration_display = _human_duration(session.started_at, session.completed_at)
    session_date = session.completed_at or session.started_at
    session_date_display = session_date.strftime('%B %d, %Y • %I:%M %p') if session_date else "--"
    template_name = session.template.name if session.template else "Workout Session"

    return_to = request.args.get('return_to')
    return_date = request.args.get('date')
    if return_to == 'calendar':
        calendar_args = {'view': 'calendar'}
        day_value = return_date or (session_date.strftime('%Y-%m-%d') if session_date else None)
        if day_value:
            calendar_args['day'] = day_value
        back_url = url_for('member.dashboard', **calendar_args)
        back_label = "Calendar"
    else:
        back_url = url_for('template.list_templates')
        back_label = "Templates"

    return render_template(
        'view-session.html',
        session=session,
        exercise_details=exercise_details,
        duration_display=duration_display,
        total_volume=int(total_volume),
        session_date_display=session_date_display,
        template_name=template_name,
        back_url=back_url,
        back_label=back_label,
        return_to=return_to,
    )
