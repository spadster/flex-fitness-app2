import json
import os

from app import create_app, db
from app.models import Food, FoodMeasure

KILOJOULE_TO_KILOCALORIE = 1 / 4.184

app = create_app()

# Directory where you'll put all your USDA JSON files
USDA_DATA_DIR = "data/usda_foods"  # Update this path

def import_usda_file(filepath, dataset_name):
    """Import foods and portions from a single USDA JSON file"""
    print(f"\n{'='*60}")
    print(f"Processing: {dataset_name}")
    print(f"{'='*60}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Different datasets have different root keys
    foods_list = None
    if 'FoundationFoods' in data:
        foods_list = data['FoundationFoods']
    elif 'SRLegacyFoods' in data:
        foods_list = data['SRLegacyFoods']
    elif 'SurveyFoods' in data:
        foods_list = data['SurveyFoods']
    elif 'BrandedFoods' in data:
        foods_list = data['BrandedFoods']
    else:
        print(f"⚠️  Unknown data format in {filepath}")
        return 0, 0
    
    foods_added = 0
    portions_added = 0
    foods_updated = 0
    
    for food_data in foods_list:
        description = food_data.get('description', '')
        if not description:
            continue
        
        fdc_id = food_data.get('fdcId')
        
        # Check if food already exists
        existing_food = Food.query.filter_by(source_id=str(fdc_id)).first()
        
        if not existing_food:
            # Extract nutrient data (per 100g)
            nutrient_amounts = {}
            energy_kcal = None

            for nutrient in food_data.get('foodNutrients', []):
                nutrient_info = nutrient.get('nutrient', {})
                name = nutrient_info.get('name')
                if not name:
                    continue

                amount = nutrient.get('amount') or 0
                unit = (nutrient_info.get('unitName') or '').lower()

                if name == 'Energy':
                    converted = amount * KILOJOULE_TO_KILOCALORIE if unit == 'kj' else amount
                    if energy_kcal is None or unit != 'kj':
                        energy_kcal = converted
                else:
                    nutrient_amounts[name] = amount

            # Create new food
            food = Food(
                name=description,
                source_id=str(fdc_id),
                calories=energy_kcal or 0,
                protein_g=nutrient_amounts.get('Protein', 0),
                carbs_g=nutrient_amounts.get('Carbohydrate, by difference', 0),
                fats_g=nutrient_amounts.get('Total lipid (fat)', 0),
                serving_size=100,
                serving_unit='g'
            )
            db.session.add(food)
            db.session.flush()  # Get the food.id
            foods_added += 1
        else:
            food = existing_food
            foods_updated += 1
        
        # Import foodPortions
        food_portions = food_data.get('foodPortions', [])
        
        if food_portions:
            for portion in food_portions:
                measure_unit = portion.get('measureUnit', {})
                measure_name = measure_unit.get('name', '').lower()
                gram_weight = portion.get('gramWeight', 0)
                
                if measure_name and gram_weight > 0:
                    # Check if measure already exists
                    existing_measure = FoodMeasure.query.filter_by(
                        food_id=food.id,
                        measure_name=measure_name
                    ).first()
                    
                    if not existing_measure:
                        measure = FoodMeasure(
                            food_id=food.id,
                            measure_name=measure_name,
                            grams=gram_weight
                        )
                        db.session.add(measure)
                        portions_added += 1
                    elif existing_measure.grams != gram_weight:
                        # Update if different
                        existing_measure.grams = gram_weight
    
    db.session.commit()
    
    print(f"✅ Foods added: {foods_added}")
    print(f"✅ Foods updated: {foods_updated}")
    print(f"✅ Portions added: {portions_added}")
    
    return foods_added, portions_added


def main():
    """Process all USDA JSON files in the directory"""
    
    if not os.path.exists(USDA_DATA_DIR):
        print(f"❌ Directory not found: {USDA_DATA_DIR}")
        print("\nPlease:")
        print("1. Create the directory")
        print("2. Download USDA datasets from: https://fdc.nal.usda.gov/download-datasets.html")
        print("3. Place JSON files in the directory")
        return
    
    json_files = [f for f in os.listdir(USDA_DATA_DIR) if f.endswith('.json')]
    
    if not json_files:
        print(f"❌ No JSON files found in {USDA_DATA_DIR}")
        return
    
    print(f"Found {len(json_files)} JSON file(s)")
    
    with app.app_context():
        total_foods = 0
        total_portions = 0
        
        for json_file in json_files:
            filepath = os.path.join(USDA_DATA_DIR, json_file)
            foods, portions = import_usda_file(filepath, json_file)
            total_foods += foods
            total_portions += portions
        
        print(f"\n{'='*60}")
        print(f"TOTAL SUMMARY")
        print(f"{'='*60}")
        print(f"✅ Total foods imported: {total_foods}")
        print(f"✅ Total portions imported: {total_portions}")
        print(f"\nDone!")


if __name__ == "__main__":
    main()