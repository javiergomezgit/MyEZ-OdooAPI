"""
MyEZ Master Import Script — Phase 1
=====================================
Runs all 4 import scripts in the correct order:
  1. sm_customers.py  — create/update Firebase Auth users + profiles
  2. sm_purchases.py  — import transactions, update units + owned_weight
  3. update_ranks.py  — recalculate typeuser, send FCM on rank-up
  4. update_leaderboard.py — recalculate monthly leaderboard scores

Usage:
    # Both CSVs
    python3 run_all.py --customers path/to/customers.csv --purchases path/to/purchases.csv

    # Customers only
    python3 run_all.py --customers path/to/customers.csv

    # Purchases only (ranks + leaderboard always run after)
    python3 run_all.py --purchases path/to/purchases.csv

Requirements:
    All dependencies from sm_customers.py, sm_purchases.py,
    update_ranks.py, update_leaderboard.py must be installed.
"""

import argparse
import importlib.util
import os
import sys
import time
from datetime import datetime, timezone

# ----------------------------------------------------------------
# Add SM-Importer to path so we can import the scripts directly
# ----------------------------------------------------------------
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)


def print_header(title):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def print_step(step, total, name):
    print(f"\n{'─' * 60}")
    print(f"  STEP {step}/{total} — {name}")
    print(f"{'─' * 60}\n")


def _load_module(name):
    """Load a script from the SM-Importer directory as a module."""
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(script_dir, f"{name}.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_all(customers_csv, purchases_csv):
    start_time = time.time()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print_header(f"MyEZ MASTER IMPORT — {now}")

    # Initialize Firebase once — all modules share the same app via the
    # guard in utils.init_firebase(), so no delete/reinit hacks are needed.
    from utils import init_firebase
    init_firebase()

    total_steps = 0
    if customers_csv:
        total_steps += 1
    if purchases_csv:
        total_steps += 1
    total_steps += 2  # update_ranks + update_leaderboard always run

    current_step = 0
    results = {}

    # ----------------------------------------------------------------
    # STEP 1 — Customers
    # ----------------------------------------------------------------
    if customers_csv:
        current_step += 1
        print_step(current_step, total_steps, "sm_customers.py — Import Users")
        try:
            mod = _load_module("sm_customers")
            results["customers"] = mod.run_import(customers_csv)
        except Exception as e:
            print(f"❌ sm_customers.py failed: {e}")
            results["customers"] = {"error": str(e)}
            print("Continuing to next step...\n")

    # ----------------------------------------------------------------
    # STEP 2 — Purchases
    # ----------------------------------------------------------------
    if purchases_csv:
        current_step += 1
        print_step(current_step, total_steps, "sm_purchases.py — Import Purchases")
        try:
            mod = _load_module("sm_purchases")
            results["purchases"] = mod.run_purchases(purchases_csv)
        except Exception as e:
            print(f"❌ sm_purchases.py failed: {e}")
            results["purchases"] = {"error": str(e)}
            print("Continuing to next step...\n")

    # ----------------------------------------------------------------
    # STEP 3 — Update Ranks
    # ----------------------------------------------------------------
    current_step += 1
    print_step(current_step, total_steps, "update_ranks.py — Recalculate Ranks + FCM")
    try:
        mod = _load_module("update_ranks")
        results["ranks"] = mod.run_update_ranks()
    except Exception as e:
        print(f"❌ update_ranks.py failed: {e}")
        results["ranks"] = {"error": str(e)}
        print("Continuing to next step...\n")

    # ----------------------------------------------------------------
    # STEP 4 — Update Leaderboard
    # ----------------------------------------------------------------
    current_step += 1
    print_step(current_step, total_steps, "update_leaderboard.py — Recalculate Leaderboard")
    try:
        mod = _load_module("update_leaderboard")
        results["leaderboard"] = mod.run_update_leaderboard()
    except Exception as e:
        print(f"❌ update_leaderboard.py failed: {e}")
        results["leaderboard"] = {"error": str(e)}

    # ----------------------------------------------------------------
    # MASTER SUMMARY
    # ----------------------------------------------------------------
    elapsed = round(time.time() - start_time, 1)
    print_header(f"MASTER SUMMARY — {elapsed}s")

    all_errors = []  # collect every error detail across all steps

    # Customers
    c = results.get("customers")
    if c:
        if "error" in c:
            print(f"  👤 Customers:     ❌ FAILED — {c['error']}")
        else:
            print(f"  👤 Customers:     ✅ {c['created']} created  |  ⏭  {c['skipped']} skipped  |  ❌ {c['errors']} errors")
            for e in c.get("error_list", []):
                all_errors.append(f"  [Customers] Row {e.get('row','?')} | {e.get('name','')} | {e.get('email','')}  →  {e.get('error','')}")

    # Purchases
    p = results.get("purchases")
    if p:
        if "error" in p:
            print(f"  🛒 Purchases:     ❌ FAILED — {p['error']}")
        else:
            print(f"  🛒 Purchases:     ✅ {p['rows_processed']} rows  |  👤 {p['users_updated']} users updated  |  ⏭  {p['skipped']} skipped  |  ❌ {p['errors']} errors")
            for e in p.get("error_list", []):
                all_errors.append(f"  [Purchases] {e.get('email','')}  →  {e.get('error','')}")

    # Ranks
    r = results.get("ranks")
    if r:
        if "error" in r:
            print(f"  🏆 Ranks:         ❌ FAILED — {r['error']}")
        else:
            print(f"  🏆 Ranks:         ✅ {r['ranks_updated']} updated  |  — {r['no_change']} unchanged  |  ❌ {r['errors']} errors")
            if r.get("updated_list"):
                for u in r["updated_list"]:
                    print(f"       ↑ {u['email']}  {u['previous_rank']} → {u['new_rank']}  ({u['weight']} lbs)")
            for e in r.get("error_list", []):
                all_errors.append(f"  [Ranks] {e.get('email','')}  →  {e.get('error','')}")

    # Leaderboard
    lb = results.get("leaderboard")
    if lb:
        if "error" in lb:
            print(f"  📊 Leaderboard:   ❌ FAILED — {lb['error']}")
        else:
            print(f"  📊 Leaderboard:   ✅ {lb['months_written']} months written  |  👤 {lb['users_processed']} users  |  ❌ {lb['errors']} errors")
            for e in lb.get("error_list", []):
                all_errors.append(f"  [Leaderboard] Month {e.get('month','?')}  →  {e.get('error','')}")

    # Print all errors in one block at the bottom
    if all_errors:
        print(f"\n  ── ERRORS ({len(all_errors)}) ──────────────────────────────────")
        for msg in all_errors:
            print(f"  ❌ {msg}")

    print(f"\n  Total time: {elapsed}s")


# ----------------------------------------------------------------
# ENTRY POINT
# ----------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MyEZ master import — runs all 4 scripts in order")
    parser.add_argument("--customers", default=None, help="Path to customers CSV file")
    parser.add_argument("--purchases", default=None, help="Path to purchases CSV file")
    args = parser.parse_args()

    if not args.customers and not args.purchases:
        print("❌ Provide at least one CSV: --customers and/or --purchases")
        sys.exit(1)

    if args.customers and not os.path.exists(args.customers):
        print(f"❌ Customers file not found: {args.customers}")
        sys.exit(1)

    if args.purchases and not os.path.exists(args.purchases):
        print(f"❌ Purchases file not found: {args.purchases}")
        sys.exit(1)

    run_all(args.customers, args.purchases)
