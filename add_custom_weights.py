from app import db, create_app
from app.models import Food, FoodMeasure

app = create_app()

# Add your custom measures here
# Format: "Food Name": {"measure": grams, "measure": grams}
CUSTOM_MEASURES = {
    "Blueberries, raw": {
        "cup": 148,
        "pint": 312,
        "handful": 75
    },
    "Strawberries, raw": {
        "cup": 152,
        "large": 18,
        "medium": 12,
        "small": 8
    },
    "Bananas, raw": {
        "cup": 150,
        "large": 136,
        "medium": 118,
        "small": 101
    },
    "Chicken breast, raw": {
        "breast": 174,
        "half breast": 87,
        "oz": 28.35
    },
    "Rice, white, cooked": {
        "cup": 158,
        "tbsp": 12.3
    },
    "Oats, dry": {
        "cup": 81,
        "half cup": 40.5
    },
    "Milk, whole": {
        "cup": 244,
        "fl oz": 30.5,
        "tbsp": 15.3
    },
    "Eggs, raw": {
        "large": 50,
        "medium": 44,
        "small": 38,
        "jumbo": 63
    },
    "Bread, whole wheat": {
        "slice": 28,
        "thick slice": 38
    },
    "Peanut butter": {
        "tbsp": 16,
        "tsp": 5.3
    },
    # Add more foods as needed...
}


def add_custom_measures():
    """Add or update custom measures for specific foods"""
    
    with app.app_context():
        print("Adding/updating custom food measures...\n")
        
        foods_found = 0
        foods_not_found = 0
        measures_added = 0
        measures_updated = 0
        
        for food_name, measures in CUSTOM_MEASURES.items():
            # Try exact match first
            food = Food.query.filter_by(name=food_name).first()
            
            # Try case-insensitive if exact match fails
            if not food:
                food = Food.query.filter(Food.name.ilike(food_name)).first()
            
            # Try partial match if still not found
            if not food:
                food = Food.query.filter(Food.name.ilike(f"%{food_name}%")).first()
            
            if food:
                foods_found += 1
                print(f"✓ Found: {food.name}")
                
                for measure_name, grams in measures.items():
                    # Check if measure exists
                    existing = FoodMeasure.query.filter_by(
                        food_id=food.id,
                        measure_name=measure_name.lower()
                    ).first()
                    
                    if existing:
                        if existing.grams != grams:
                            print(f"  ↻ Updating {measure_name}: {existing.grams}g → {grams}g")
                            existing.grams = grams
                            measures_updated += 1
                        else:
                            print(f"  ✓ {measure_name}: {grams}g (already correct)")
                    else:
                        print(f"  + Adding {measure_name}: {grams}g")
                        new_measure = FoodMeasure(
                            food_id=food.id,
                            measure_name=measure_name.lower(),
                            grams=grams
                        )
                        db.session.add(new_measure)
                        measures_added += 1
                
                print()  # Blank line between foods
            else:
                foods_not_found += 1
                print(f"✗ NOT FOUND: {food_name}")
                print()
        
        db.session.commit()
        
        # Summary
        print("="*60)
        print("SUMMARY")
        print("="*60)
        print(f"✓ Foods found: {foods_found}")
        print(f"✗ Foods not found: {foods_not_found}")
        print(f"+ Measures added: {measures_added}")
        print(f"↻ Measures updated: {measures_updated}")
        print("\n✅ Done!")


def search_food(search_term):
    """Helper function to find foods in your database"""
    with app.app_context():
        foods = Food.query.filter(Food.name.ilike(f"%{search_term}%")).limit(20).all()
        
        if foods:
            print(f"\nFound {len(foods)} food(s) matching '{search_term}':\n")
            for food in foods:
                print(f"  - {food.name} (ID: {food.id})")
                measures = FoodMeasure.query.filter_by(food_id=food.id).all()
                if measures:
                    for m in measures:
                        print(f"      └─ {m.measure_name}: {m.grams}g")
                else:
                    print(f"      └─ No measures")
        else:
            print(f"\n✗ No foods found matching '{search_term}'")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Search mode: python add_measures.py search chicken
        if sys.argv[1] == "search" and len(sys.argv) > 2:
            search_food(" ".join(sys.argv[2:]))
        else:
            print("Usage: python add_measures.py search <food_name>")
    else:
        # Default: add/update custom measures
        add_custom_measures()