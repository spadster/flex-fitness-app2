from flask import Blueprint, render_template, session
from app import db
from app.models import User
from flask_login import login_required, current_user

trainer_bp = Blueprint('trainer', __name__)

@trainer_bp.route('/trainer/clients')
def view_clients():
    trainer_id = session.get('user_id')  # the logged-in trainer
    if not trainer_id:
        return "Please log in first", 403

    # Only fetch members assigned to this trainer
    clients = User.query.filter_by(trainer_id=trainer_id, role='member').all()

    return render_template('display-trainer.html', clients=clients)

@trainer_bp.route('/dashboard-trainer')
@login_required
def dashboard_trainer():
    if current_user.role != 'trainer':
        return "Access denied", 403
    return render_template('dashboard-trainer.html', trainer=current_user)