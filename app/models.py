from app import db, login_manager
from datetime import datetime
import string, random
from flask_login import UserMixin
import pytz

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'trainer' or 'member'
    trainer_code = db.Column(db.String(6), unique=True, nullable=True)
    # Email verification
    email_verified = db.Column(db.Boolean, default=False)
    email_verification_token = db.Column(db.String(128), nullable=True)
    email_verification_sent_at = db.Column(db.DateTime, nullable=True)
    password_reset_token = db.Column(db.String(128), nullable=True)
    password_reset_sent_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    custom_calorie_target = db.Column(db.Float, nullable=True)
    custom_protein_target_g = db.Column(db.Float, nullable=True)
    custom_carb_target_g = db.Column(db.Float, nullable=True)
    custom_fat_target_g = db.Column(db.Float, nullable=True)
    theme_mode = db.Column(db.String(20), nullable=True, default="light")
    macro_target_mode = db.Column(db.String(20), nullable=True)
    macro_ratio_protein = db.Column(db.Float, nullable=True)
    macro_ratio_carbs = db.Column(db.Float, nullable=True)
    macro_ratio_fats = db.Column(db.Float, nullable=True)

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
    trainer_meals = db.relationship(
        'TrainerMeal',
        foreign_keys='TrainerMeal.member_id',
        backref='member',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )
    created_meals = db.relationship(
        'TrainerMeal',
        foreign_keys='TrainerMeal.trainer_id',
        backref='trainer',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )
    member_meals = db.relationship(
        'MemberMeal',
        backref='creator',
        cascade='all, delete-orphan',
        lazy='dynamic'
    )

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
    "teaspoon": 4.2,
    "teaspoons": 4.2,
    "tbsp": 14.3,
    "tbs": 14.3,
    "tablespoon": 14.3,
    "tablespoons": 14.3,
    "cup": 240,
    "cups": 240,
    "fl oz": 29.5735,
    "floz": 29.5735,
    "fluid ounce": 29.5735,
    "fluid ounces": 29.5735,
    "ml": 1,
    "milliliter": 1,
    "milliliters": 1,
    "l": 1000,
    "liter": 1000,
    "liters": 1000
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
        from app.services.nutrition import scale_food_nutrients
        quantity_in_grams = self.quantity_in_grams()
        scaled = scale_food_nutrients(self.food, quantity_in_grams)

        return {
            "calories": round(scaled["calories"], 1),
            "protein": round(scaled["protein"], 1),
            "carbs": round(scaled["carbs"], 1),
            "fats": round(scaled["fats"], 1)
        }


class TrainerMeal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    meal_slot = db.Column(db.String(20), nullable=False, default='meal1')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    ingredients = db.relationship(
        'TrainerMealIngredient',
        backref='meal',
        cascade='all, delete-orphan',
        order_by='TrainerMealIngredient.position'
    )


class TrainerMealIngredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    meal_id = db.Column(db.Integer, db.ForeignKey('trainer_meal.id'), nullable=False)
    food_id = db.Column(db.Integer, db.ForeignKey('food.id'), nullable=False)
    quantity_value = db.Column(db.Float, nullable=True)
    quantity_unit = db.Column(db.String(50), nullable=True)
    quantity_grams = db.Column(db.Float, nullable=False)
    volume_ml = db.Column(db.Float, nullable=True)
    position = db.Column(db.Integer, default=0)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    food = db.relationship('Food')


class MemberMeal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    meal_slot = db.Column(db.String(20), nullable=False, default='meal1')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    ingredients = db.relationship(
        'MemberMealIngredient',
        backref='member_meal',
        cascade='all, delete-orphan',
        order_by='MemberMealIngredient.position'
    )


class MemberMealIngredient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    meal_id = db.Column(db.Integer, db.ForeignKey('member_meal.id'), nullable=False)
    food_id = db.Column(db.Integer, db.ForeignKey('food.id'), nullable=False)
    quantity_value = db.Column(db.Float, nullable=True)
    quantity_unit = db.Column(db.String(50), nullable=True)
    quantity_grams = db.Column(db.Float, nullable=False)
    volume_ml = db.Column(db.Float, nullable=True)
    position = db.Column(db.Integer, default=0)
    notes = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    food = db.relationship('Food')
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


# -----------------------------
# Exercise Planner Models
# -----------------------------
class ExerciseTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    owner = db.relationship('User', backref=db.backref('exercise_templates', lazy='dynamic'))
    exercises = db.relationship('TemplateExercise', backref='template', cascade="all, delete-orphan")


class TemplateExercise(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('exercise_template.id'), nullable=False)
    exercise_name = db.Column(db.String(200), nullable=False)
    muscle = db.Column(db.String(100))
    equipment = db.Column(db.String(100))
    default_sets = db.Column(db.Integer)
    default_reps = db.Column(db.Integer)


class ExerciseCatalog(db.Model):
    __tablename__ = 'exercise_catalog'

    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(200), nullable=False, index=True)
    force = db.Column(db.String(50))
    level = db.Column(db.String(50))
    mechanic = db.Column(db.String(50))
    equipment = db.Column(db.String(100), index=True)
    category = db.Column(db.String(100), index=True)
    primary_muscles = db.Column(db.String(200), index=True)
    secondary_muscles = db.Column(db.String(200))
    instructions = db.Column(db.Text)
    image_main = db.Column(db.String(255))
    image_secondary = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AssignedTemplate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    template_id = db.Column(db.Integer, db.ForeignKey('exercise_template.id'), nullable=False)
    trainer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

    template = db.relationship('ExerciseTemplate', backref=db.backref('assignments', lazy='dynamic'))
    trainer = db.relationship('User', foreign_keys=[trainer_id])
    member = db.relationship('User', foreign_keys=[member_id])


class WorkoutSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    template_id = db.Column(db.Integer, db.ForeignKey('exercise_template.id'))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    summary = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text)

    user = db.relationship('User', backref=db.backref('workout_sessions', lazy='dynamic'))
    template = db.relationship('ExerciseTemplate')
    sets = db.relationship('WorkoutSet', backref='session', cascade="all, delete-orphan")


class WorkoutSet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('workout_session.id'), nullable=False)
    template_exercise_id = db.Column(db.Integer, db.ForeignKey('template_exercise.id'))
    exercise_name = db.Column(db.String(200), nullable=False)
    set_number = db.Column(db.Integer, nullable=False, default=1)
    reps = db.Column(db.Integer, nullable=False)
    weight = db.Column(db.Float)

    template_exercise = db.relationship('TemplateExercise')


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    trainer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime, nullable=True)

    trainer = db.relationship(
        'User',
        foreign_keys=[trainer_id],
        backref=db.backref('sent_messages', lazy='dynamic')
    )
    client = db.relationship(
        'User',
        foreign_keys=[client_id],
        backref=db.backref('received_messages', lazy='dynamic')
    )
    @property
    def local_timestamp(self):
        est = pytz.timezone("America/New_York")
        return self.timestamp.replace(tzinfo=pytz.utc).astimezone(est)
