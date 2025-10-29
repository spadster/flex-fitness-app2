from app import db
from datetime import datetime
import string, random

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'trainer' or 'member'
    trainer_code = db.Column(db.String(6), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 🔹 Link each member to a trainer
    trainer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # 🔹 Self-referential relationship
    trainer = db.relationship(
        'User',
        remote_side=[id],
        backref=db.backref('members', lazy='dynamic')
    )

    # 🔹 Relationships
    progress = db.relationship("Progress", backref="user", cascade="all, delete-orphan")
    food_logs = db.relationship("UserFoodLog", backref="user", lazy=True)

    def generate_trainer_code(self):
        if self.role == 'trainer' and not self.trainer_code:
            characters = string.ascii_uppercase + string.digits
            self.trainer_code = ''.join(random.choices(characters, k=6))
            
class Food(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    calories = db.Column(db.Float)
    protein_g = db.Column(db.Float)
    carbs_g = db.Column(db.Float)
    fats_g = db.Column(db.Float)
    source_id = db.Column(db.String(100))

class UserFoodLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    food_id = db.Column(db.Integer, db.ForeignKey("food.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    log_date = db.Column(db.Date, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    food = db.relationship("Food")

class Progress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    weight = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)

class Exercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    reps = db.Column(db.Integer, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    # support date/log_date naming used by routes
    date = db.Column(db.DateTime, nullable=True)
    log_date = db.Column(db.Date, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)