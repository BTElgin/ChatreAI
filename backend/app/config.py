import os

DEFAULT_BOOKING_URL = (
    "https://calendar.google.com/PLACEHOLDER-set-BOOKING_URL-env-var-to-a-real-appointment-schedule-link"
)
BOOKING_URL = os.environ.get("BOOKING_URL", DEFAULT_BOOKING_URL)
