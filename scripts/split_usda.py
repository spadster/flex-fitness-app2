import json
import os

INPUT_FILE = "data/usda_foods/SRLegacyFoods.json"
OUTPUT_DIR = "data/usda_foods/split"
MAX_CHUNK_SIZE = 90 * 1024 * 1024  # 90 MB

os.makedirs(OUTPUT_DIR, exist_ok=True)

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    raw_data = json.load(f)

# Check the type
if isinstance(raw_data, dict):
    # If it's a dict, we need the actual list inside it
    # For USDA SRLegacyFoods.json, usually it's under 'SRLegacyFoods'
    data = raw_data.get("SRLegacyFoods", [])
elif isinstance(raw_data, list):
    data = raw_data
else:
    raise ValueError("Unexpected JSON structure in SRLegacyFoods.json")

print(f"Total items to split: {len(data)}")

chunks = []
current_chunk = []
current_size = 0

for item in data:
    item_json = json.dumps(item, ensure_ascii=False)
    item_size = len(item_json.encode("utf-8"))

    if current_size + item_size > MAX_CHUNK_SIZE:
        chunks.append(current_chunk)
        current_chunk = []
        current_size = 0

    current_chunk.append(item)
    current_size += item_size

if current_chunk:
    chunks.append(current_chunk)

for idx, chunk in enumerate(chunks, 1):
    output_path = os.path.join(OUTPUT_DIR, f"SRLegacyFoods_part{idx}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(chunk, f, ensure_ascii=False, separators=(',', ':'))
    print(f"Saved {output_path} ({len(chunk)} items)")
