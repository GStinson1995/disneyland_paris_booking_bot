#!/usr/bin/env python3
"""
Disneyland Paris dining availability checker.

Polls the (undocumented, but keyless-for-users) booking API that
bookrestaurants.disneylandparis.com itself uses, for a fixed set of
restaurants/dates/meal periods, and sends a Telegram message the moment
a slot that wasn't available before shows up as available.

State (which slots were available on the last run) is kept in state.json
so we only notify on *new* availability, not on every single run.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

API_URL = "https://dlp-is-sales-drs-book-dine.wdprapps.disney.com/prod/v4/book-dine/availabilities/en-gb"
API_KEY = "AaQHDoRgDa66dl2PQuTEe9DjyBlH8ylV4LxnldFY"

# restaurantId -> friendly name
RESTAURANTS = {
    "P2TR02": "Bistrot Chez Rémy",
    "P2AR02": "PYM Kitchen",
    "H02R04": "Downtown Restaurant (Hotel New York - The Art of Marvel)",
}

DATES = ["2026-10-07", "2026-10-08", "2026-10-09"]
PARTY_MIX = 3  # 2 adults + 1 child, matches the on-file booking
MEAL_PERIODS_OF_INTEREST = {"Lunch", "Dinner"}

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
    "content-type": "application/json",
    "origin": "https://bookrestaurants.disneylandparis.com",
    "referer": "https://bookrestaurants.disneylandparis.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
    "x-api-key": API_KEY,
}


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"slots": {}, "consecutive_failures": 0, "blocked_notified": False}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
        f.write("\n")


def send_telegram(message: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram credentials not set - skipping send. Message would have been:")
        print(message)
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        },
        timeout=15,
    )
    resp.raise_for_status()


def check_availability(restaurant_id: str, date: str):
    body = {
        "partyMix": PARTY_MIX,
        "session": 0,
        "restaurantId": restaurant_id,
        "sourceSite": "web",
        "date": date,
    }
    resp = requests.post(
        API_URL,
        params={"scope": "Restaurant"},
        headers=HEADERS,
        json=body,
        timeout=20,
    )
    if resp.status_code != 200:
        # Surface the actual response body (truncated) so failures are
        # diagnosable from the Actions log instead of just "400 Bad Request".
        raise RuntimeError(
            f"{resp.status_code} {resp.reason} - body: {resp.text[:500]!r}"
        )
    return resp.json()


def extract_available_slots(data, meal_periods_of_interest=MEAL_PERIODS_OF_INTEREST):
    """Given the raw API response for one restaurant/date, return a sorted
    list of "<MealPeriod> <time>" strings for slots that are available."""
    available = []
    for day in data:
        for meal in day.get("mealPeriods", []):
            period_name = meal.get("mealPeriod")
            if period_name not in meal_periods_of_interest:
                continue
            for slot in meal.get("slotList", []):
                if str(slot.get("available")).lower() == "true":
                    available.append(f"{period_name} {slot.get('time')}")
    return sorted(available)


def main():
    state = load_state()
    slot_state = state.get("slots", {})
    new_slot_state = {}
    newly_available = []
    errors = []

    for restaurant_id, restaurant_name in RESTAURANTS.items():
        for date in DATES:
            key = f"{restaurant_id}|{date}"
            try:
                data = check_availability(restaurant_id, date)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{restaurant_name} {date}: {e}")
                if key in slot_state:
                    new_slot_state[key] = slot_state[key]
                continue

            available_slots = extract_available_slots(data)
            new_slot_state[key] = available_slots

            previously_available = set(slot_state.get(key, []))
            now_available = set(available_slots)
            newly_opened = now_available - previously_available
            if newly_opened:
                newly_available.append((restaurant_name, date, sorted(newly_opened)))

    total_checks = len(RESTAURANTS) * len(DATES)
    all_failed = len(errors) == total_checks

    # Track consecutive total failures so we alert once on "looks blocked"
    # rather than every 15 minutes.
    if all_failed:
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
    else:
        if state.get("consecutive_failures", 0) >= 3 and state.get("blocked_notified"):
            send_telegram(
                "The DLP table checker is back to getting responses from Disney "
                "after previously failing - resuming normal checks."
            )
        state["consecutive_failures"] = 0
        state["blocked_notified"] = False

    if all_failed and state["consecutive_failures"] == 3 and not state.get("blocked_notified"):
        send_telegram(
            "⚠️ The DLP table checker has failed 3 checks in a row "
            "(Disney's API is erroring or blocking requests). "
            "It'll keep retrying quietly, but you may want to check on it.\n\n"
            "Last errors:\n" + "\n".join(errors[:3])
        )
        state["blocked_notified"] = True

    state["slots"] = new_slot_state
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)

    if newly_available:
        lines = ["🎉 <b>A Disneyland Paris table just opened up!</b>"]
        for name, date, slots in newly_available:
            lines.append(f"\n<b>{name}</b> — {date}")
            for s in slots:
                lines.append(f"  • {s}")
        lines.append("\n👉 Book now: https://bookrestaurants.disneylandparis.com/")
        message = "\n".join(lines)
        send_telegram(message)
        print("Sent notification for:", newly_available)
    else:
        print(f"No new availability. {len(errors)}/{total_checks} checks failed.")
        if errors:
            print("Errors:", errors)

    # Non-zero exit on total failure makes it easy to spot in the Actions
    # tab, without needing to read logs.
    if all_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
