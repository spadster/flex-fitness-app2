from datetime import datetime

from flask import Blueprint, render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import User, UserFoodLog, Progress

trainer_bp = Blueprint('trainer', __name__, url_prefix='/trainer')

@trainer_bp.route('/dashboard-trainer')
@login_required
def dashboard_trainer():
    if current_user.role != 'trainer':
        flash("Access denied.", "danger")
        return redirect(url_for('main.home'))

    today = datetime.utcnow().date()
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