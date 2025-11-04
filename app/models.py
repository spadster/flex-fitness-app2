from app import db, login_manager
from datetime import datetime
import string, random
from flask_login import UserMixin

class User(db.Model, UserMixin):
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

    # Profile details for nutrition goals
    gender = db.Column(db.String(20), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    height_cm = db.Column(db.Float, nullable=True)
    activity_level = db.Column(db.Float, nullable=True)
    maintenance_calories = db.Column(db.Float, nullable=True)
    calorie_goal = db.Column(db.Float, nullable=True)
    goal_weight_kg = db.Column(db.Float, nullable=True)
    weekly_weight_change_lbs = db.Column(db.Float, nullable=True)
    
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

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
            
class Food(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    calories = db.Column(db.Float)
    protein_g = db.Column(db.Float)
    carbs_g = db.Column(db.Float)
    fats_g = db.Column(db.Float)
    source_id = db.Column(db.String(100))
    serving_size = db.Column(db.Float)
    serving_unit = db.Column(db.String(50))
    grams_per_unit = db.Column(db.Float)

# Make sure this is defined somewhere
UNIT_TO_GRAMS = {
    "g": 1,
    "kg": 1000,
    "oz": 28.35,
    "lb": 453.592,
    "tsp": 4.2,   # approximate
    "tbsp": 14.3,
    "cup": 240
}

class UserFoodLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    food_id = db.Column(db.Integer, db.ForeignKey("food.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), default="g")  # <--- add this column
    log_date = db.Column(db.Date, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    food = db.relationship("Food")

    def quantity_in_grams(self):
        """Convert the logged quantity to grams based on the unit."""
        quantity = self.quantity or 0
        unit = (self.unit or "g").lower()

        if unit == "g":
            return quantity
        
        measure = FoodMeasure.query.filter_by(food_id=self.food_id, measure_name=unit).first()
        if measure:
            return quantity * measure.grams
        
        grams_per_unit = UNIT_TO_GRAMS.get(unit)
        if grams_per_unit:
            return quantity * grams_per_unit
        
        return quantity  # Fallback to original quantity if unit is unknown
    
    @property
    def scaled(self):
        from app.routes.member import _scale_food_nutrients
        quantity_in_grams = self.quantity_in_grams()
        scaled = _scale_food_nutrients(self.food, quantity_in_grams)

        return {
            "calories": round(scaled["calories"], 1),
            "protein": round(scaled["protein"], 1),
            "carbs": round(scaled["carbs"], 1),
            "fats": round(scaled["fats"], 1)
        }
class Progress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    weight = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)

class FoodMeasure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    food_id = db.Column(db.Integer, db.ForeignKey('food.id'))
    measure_name = db.Column(db.String(50))  # "cup", "tbsp", "tsp", "slice"
    grams = db.Column(db.Float)              # how many grams that measure is

    food = db.relationship("Food", backref="measures")
