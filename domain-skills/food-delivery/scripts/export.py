"""Phase 4: Merge, dedup, and export food delivery data.

Combines restaurant and menu data from both platforms into unified CSV/JSON.

Usage:
    .venv/bin/python3 scripts/export.py --restaurants dd.json ue.json --menus dd_m.json ue_m.json --output food_data
"""
import argparse, csv, json, sys
from pathlib import Path
from datetime import datetime


CSV_FIELDNAMES = [
    "platform",
    "store_id",
    "store_name",
    "store_url",
    "store_rating",
    "store_delivery_fee",
    "store_delivery_time_min",
    "store_delivery_time_max",
    "store_promo",
    "category",
    "item_name",
    "item_price",
    "description",
    "popular_badge",
    "extracted_at",
]


def load_json(path):
    if not path or not Path(path).exists():
        return None
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        return data.get("restaurants") or data.get("menu_items") or data
    return data


def fill_rates(records, fields):
    """Compute fill rate per field."""
    if not records:
        return {}
    rates = {}
    for f in fields:
        filled = sum(1 for r in records if r.get(f) is not None and r.get(f) != "")
        rates[f] = {"filled": filled, "total": len(records), "rate": round(filled / len(records), 3)}
    return rates


def export_csv(restaurants, menus, output_path):
    """Export flat CSV: one row per menu item, joined with restaurant metadata."""
    rest_by_id = {}
    for r in (restaurants or []):
        key = f"{r.get('platform')}::{r.get('store_id')}"
        rest_by_id[key] = r

    rows = []
    for item in (menus or []):
        key = f"{item.get('platform')}::{item.get('store_id')}"
        rest = rest_by_id.get(key, {})
        rows.append({
            "platform": item.get("platform", ""),
            "store_id": item.get("store_id", ""),
            "store_name": item.get("store_name", rest.get("name", "")),
            "store_url": rest.get("url", ""),
            "store_rating": rest.get("rating", ""),
            "store_delivery_fee": rest.get("delivery_fee", ""),
            "store_delivery_time_min": rest.get("delivery_time_min", ""),
            "store_delivery_time_max": rest.get("delivery_time_max", ""),
            "store_promo": rest.get("promo_badge", ""),
            "category": item.get("category", ""),
            "item_name": item.get("item_name", ""),
            "item_price": item.get("item_price", ""),
            "description": item.get("description", ""),
            "popular_badge": item.get("popular_badge", ""),
            "extracted_at": item.get("extracted_at", ""),
        })

    csv_path = f"{output_path}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV: {csv_path} ({len(rows)} rows)")
    return rows


def export_structured_json(restaurants, menus, output_path):
    """Export structured JSON with restaurants as keys, menus nested."""
    rest_by_id = {}
    for r in (restaurants or []):
        key = f"{r.get('platform')}::{r.get('store_id')}"
        rest_by_id[key] = {**r, "menu_items": []}

    for item in (menus or []):
        key = f"{item.get('platform')}::{item.get('store_id')}"
        if key in rest_by_id:
            rest_by_id[key]["menu_items"].append(item)

    json_path = f"{output_path}.json"
    output = {
        "exported_at": datetime.now().isoformat(),
        "total_restaurants": len(rest_by_id),
        "total_menu_items": len(menus or []),
        "restaurants": list(rest_by_id.values()),
    }
    Path(json_path).write_text(json.dumps(output, indent=2, default=str, ensure_ascii=False))
    print(f"JSON: {json_path} ({len(rest_by_id)} restaurants)")


def export_coverage(restaurants, menus, output_path):
    """Export coverage report with field fill rates."""
    rest_fields = ["store_id", "name", "url", "rating", "delivery_fee", "delivery_time_min"]
    menu_fields = ["item_name", "item_price", "description", "category", "popular_badge"]

    coverage = {
        "exported_at": datetime.now().isoformat(),
        "restaurants": {
            "count": len(restaurants or []),
            "fill_rates": fill_rates(restaurants or [], rest_fields),
        },
        "menu_items": {
            "count": len(menus or []),
            "fill_rates": fill_rates(menus or [], menu_fields),
        },
    }
    cov_path = f"{output_path}_coverage.json"
    Path(cov_path).write_text(json.dumps(coverage, indent=2, default=str))
    print(f"Coverage: {cov_path}")
    return coverage


def main():
    parser = argparse.ArgumentParser(description="Export food delivery data")
    parser.add_argument("--restaurants", nargs="+", help="Restaurant JSON files from Phase 2")
    parser.add_argument("--menus", nargs="+", help="Menu JSON files from Phase 3")
    parser.add_argument("--output", required=True, help="Output path prefix (extensions added automatically)")
    args = parser.parse_args()

    # Load all restaurant files
    all_restaurants = []
    for path in (args.restaurants or []):
        data = load_json(path)
        if isinstance(data, list):
            all_restaurants.extend(data)
        elif isinstance(data, dict) and "restaurants" in data:
            all_restaurants.extend(data["restaurants"])

    # Load all menu files
    all_menus = []
    for path in (args.menus or []):
        data = load_json(path)
        if isinstance(data, list):
            all_menus.extend(data)
        elif isinstance(data, dict) and "menu_items" in data:
            all_menus.extend(data["menu_items"])

    print(f"Loaded {len(all_restaurants)} restaurants, {len(all_menus)} menu items")

    # Dedup restaurants by (platform, store_id)
    seen_rest = set()
    deduped_rest = []
    for r in all_restaurants:
        key = f"{r.get('platform')}::{r.get('store_id')}"
        if key not in seen_rest:
            seen_rest.add(key)
            deduped_rest.append(r)

    # Dedup menus by (platform, store_id, item_name)
    seen_menu = set()
    deduped_menu = []
    for m in all_menus:
        key = f"{m.get('platform')}::{m.get('store_id')}::{m.get('item_name')}"
        if key not in seen_menu:
            seen_menu.add(key)
            deduped_menu.append(m)

    print(f"After dedup: {len(deduped_rest)} restaurants, {len(deduped_menu)} menu items")

    # Export
    export_csv(deduped_rest, deduped_menu, args.output)
    export_structured_json(deduped_rest, deduped_menu, args.output)
    coverage = export_coverage(deduped_rest, deduped_menu, args.output)

    print(f"\nCoverage summary:")
    if coverage["restaurants"]["count"] > 0:
        print(f"  Restaurants: {coverage['restaurants']['count']}")
        for field, stats in coverage["restaurants"]["fill_rates"].items():
            print(f"    {field}: {stats['rate']:.0%} ({stats['filled']}/{stats['total']})")
    if coverage["menu_items"]["count"] > 0:
        print(f"  Menu items: {coverage['menu_items']['count']}")
        for field, stats in coverage["menu_items"]["fill_rates"].items():
            print(f"    {field}: {stats['rate']:.0%} ({stats['filled']}/{stats['total']})")


if __name__ == "__main__":
    main()
