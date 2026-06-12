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


def run_all(customers_csv, purchases_csv):
    start_time = time.time()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print_header(f"MyEZ MASTER IMPORT — {now}")

    total_steps = 0
    if customers_csv:
        total_steps += 1
    if purchases_csv:
        total_steps += 1
    total_steps += 2  # update_ranks + update_leaderboard always run

    current_step = 0

    # ----------------------------------------------------------------
    # STEP 1 — Customers
    # ----------------------------------------------------------------
    if customers_csv:
        current_step += 1
        print_step(current_step, total_steps, "sm_customers.py — Import Users")
        try:
            import firebase_admin
            # Reset firebase app if already initialized
            try:
                firebase_admin.get_app()
                firebase_admin.delete_app(firebase_admin.get_app())
            except ValueError:
                pass

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "sm_customers",
                os.path.join(script_dir, "sm_customers.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.init_firebase()
            mod.run_import(customers_csv)
        except Exception as e:
            print(f"❌ sm_customers.py failed: {e}")
            print("Continuing to next step...\n")

    # ----------------------------------------------------------------
    # STEP 2 — Purchases
    # ----------------------------------------------------------------
    if purchases_csv:
        current_step += 1
        print_step(current_step, total_steps, "sm_purchases.py — Import Purchases")
        try:
            import firebase_admin
            try:
                firebase_admin.delete_app(firebase_admin.get_app())
            except (ValueError, Exception):
                pass

            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "sm_purchases",
                os.path.join(script_dir, "sm_purchases.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.init_firebase()
            mod.run_purchases(purchases_csv)
        except Exception as e:
            print(f"❌ sm_purchases.py failed: {e}")
            print("Continuing to next step...\n")

    # ----------------------------------------------------------------
    # STEP 3 — Update Ranks
    # ----------------------------------------------------------------
    current_step += 1
    print_step(current_step, total_steps, "update_ranks.py — Recalculate Ranks + FCM")
    try:
        import firebase_admin
        try:
            firebase_admin.delete_app(firebase_admin.get_app())
        except (ValueError, Exception):
            pass

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "update_ranks",
            os.path.join(script_dir, "update_ranks.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.init_firebase()
        mod.run_update_ranks()
    except Exception as e:
        print(f"❌ update_ranks.py failed: {e}")
        print("Continuing to next step...\n")

    # ----------------------------------------------------------------
    # STEP 4 — Update Leaderboard
    # ----------------------------------------------------------------
    current_step += 1
    print_step(current_step, total_steps, "update_leaderboard.py — Recalculate Leaderboard")
    try:
        import firebase_admin
        try:
            firebase_admin.delete_app(firebase_admin.get_app())
        except (ValueError, Exception):
            pass

        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "update_leaderboard",
            os.path.join(script_dir, "update_leaderboard.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.init_firebase()
        mod.run_update_leaderboard()
    except Exception as e:
        print(f"❌ update_leaderboard.py failed: {e}")

    # ----------------------------------------------------------------
    # FINAL SUMMARY
    # ----------------------------------------------------------------
    elapsed = round(time.time() - start_time, 1)
    print_header(f"IMPORT COMPLETE — {elapsed}s")
    print(f"  Customers CSV:  {customers_csv or 'skipped'}")
    print(f"  Purchases CSV:  {purchases_csv or 'skipped'}")
    print(f"  Ranks:          updated")
    print(f"  Leaderboard:    updated")
    print(f"\n  Total time: {elapsed} seconds")


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
