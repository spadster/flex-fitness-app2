from app import db, create_app
from app.models import Food, FoodMeasure

app = create_app()

with app.app_context():
    # Check blueberries specifically
    blueberries = Food.query.filter(Food.name.ilike('%blueberr%')).first()
    
    if blueberries:
        print(f"Food: {blueberries.name}")
        print(f"Food ID: {blueberries.id}")
        print(f"Serving size: {blueberries.serving_size}")
        print(f"\nMeasures for this food:")
        measures = FoodMeasure.query.filter_by(food_id=blueberries.id).all()
        if measures:
            for measure in measures:
                print(f"  - {measure.measure_name}: {measure.grams}g")
        else:
            print("  NO MEASURES FOUND!")
    else:
        print("Blueberries not found in database")