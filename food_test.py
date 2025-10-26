from app import create_app, db
from app.models import Food

app = create_app()

with app.app_context():
    foods = Food.query.limit(10).all()
    for f in foods:
        print(f.name, f.calories, f.protein_g, f.carbs_g, f.fats_g)
