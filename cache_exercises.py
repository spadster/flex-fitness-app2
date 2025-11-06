"""Utility script to cache the Free Exercise DB dataset locally.

Usage::

    python scripts/cache_exercises.py

This script requires an application context, so run it from the project
root with the virtualenv activated. It will download the latest JSON
from GitHub, upsert rows in the ``exercise_catalog`` table, and remove any
entries that no longer exist in the upstream dataset.
"""

from __future__ import annotations

import argparse
import sys
from typing import Iterable

import requests

from app import create_app, db
from app.models import ExerciseCatalog

EXERCISE_SOURCE_URL = "https://raw.githubusercontent.com/yuhonas/free-exercise-db/main/dist/exercises.json"


def _flatten_list(values: Iterable[str] | None) -> str | None:
    if not values:
        return None
    return ", ".join(v.strip() for v in values if v and v.strip()) or None


def _flatten_instructions(values: Iterable[str] | None) -> str | None:
    if not values:
        return None
    cleaned = [v.strip() for v in values if v and v.strip()]
    return "\n".join(cleaned) if cleaned else None


def fetch_dataset(url: str = EXERCISE_SOURCE_URL) -> list[dict]:
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError("Unexpected payload when fetching exercise dataset")
    return data


def upsert_catalog(data: list[dict], delete_missing: bool = True) -> tuple[int, int, int]:
    existing = {row.source_id: row for row in ExerciseCatalog.query.all()}
    seen_ids: set[str] = set()

    created = 0
    updated = 0

    for item in data:
        source_id = str(item.get("id") or item.get("name"))
        if not source_id:
            continue
        seen_ids.add(source_id)

        row = existing.get(source_id)
        if row is None:
            row = ExerciseCatalog(source_id=source_id)
            db.session.add(row)
            created += 1
        else:
            updated += 1

        row.name = item.get("name") or source_id
        row.force = item.get("force")
        row.level = item.get("level")
        row.mechanic = item.get("mechanic")
        row.equipment = item.get("equipment")
        row.category = item.get("category")
        row.primary_muscles = _flatten_list(item.get("primaryMuscles"))
        row.secondary_muscles = _flatten_list(item.get("secondaryMuscles"))
        row.instructions = _flatten_instructions(item.get("instructions"))

        images = item.get("images") or []
        row.image_main = images[0] if len(images) > 0 else None
        row.image_secondary = images[1] if len(images) > 1 else None

    deleted = 0
    if delete_missing:
        for source_id, row in existing.items():
            if source_id not in seen_ids:
                db.session.delete(row)
                deleted += 1

    db.session.commit()
    return created, updated, deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Cache the Free Exercise DB dataset locally")
    parser.add_argument(
        "--no-delete",
        action="store_true",
        help="Do not delete catalog entries that disappear from the upstream dataset.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        data = fetch_dataset()
        created, updated, deleted = upsert_catalog(data, delete_missing=not args.no_delete)

    print(f"Exercises created: {created}")
    print(f"Exercises updated: {updated}")
    if not args.no_delete:
        print(f"Exercises deleted: {deleted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
