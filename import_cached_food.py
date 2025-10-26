import json
from app import create_app, db
from app.models import Food

CACHE_FILE = "data/cache/foods_cache.json"
app = create_app()

with app.app_context():
    with open(CACHE_FILE, encoding="utf-8") as f:
        foods = json.load(f)

    for fitem in foods:
        if Food.query.filter_by(source_id=fitem["fdc_id"]).first():
            continue
        food = Food(**{
            "name": fitem["name"],
            "source_id": fitem["fdc_id"],
            "calories": fitem["calories"],
            "protein_g": fitem["protein_g"],
            "carbs_g": fitem["carbs_g"],
            "fats_g": fitem["fats_g"]
        })
        db.session.add(food)
    db.session.commit()
    print(f"✅ Imported {len(foods)} foods from cache!")
