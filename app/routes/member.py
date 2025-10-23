from flask import Blueprint, render_template, session, flash, redirect, request, url_for
from app import db
from app.models import User, Progress

member_bp = Blueprint('member', __name__)

@member_bp.route('/member/progress')
def view_progress():
    # Ensure the user is logged in
    user_id = session.get('user_id')
    role = session.get('role')

    if not user_id or role != 'member':
        return "Access denied", 403

    # Fetch the member from the database
    member = User.query.get(user_id)
    if not member:
        return "Member not found", 404

    # Get all progress records for this member
    progress_entries = Progress.query.filter_by(user_id=user_id).order_by(Progress.date.desc()).all()

    return render_template('display-member.html', user=member, progress_entries=progress_entries)

@member_bp.route('/register-trainer', methods=['POST'])
def register_trainer():
    # Get current member from session
    member_id = session.get('user_id')
    if not member_id:
        return "Please log in first", 403

    member = User.query.get(member_id)
    trainer_code = request.form.get("trainer_code", "").upper().strip()

    # Validate trainer
    trainer = User.query.filter_by(trainer_code=trainer_code, role='trainer').first()
    if not trainer:
        flash("Invalid trainer code.")
        return redirect(request.referrer)

    # Assign trainer
    member.trainer_id = trainer.id
    db.session.commit()
    flash(f"You are now registered with trainer {trainer.first_name} {trainer.last_name}.")

    return redirect(request.referrer)  # stay on the same page
