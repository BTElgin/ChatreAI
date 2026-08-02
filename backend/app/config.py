import os

DEFAULT_BOOKING_URL = (
    "https://calendar.google.com/PLACEHOLDER-set-BOOKING_URL-env-var-to-a-real-appointment-schedule-link"
)
BOOKING_URL = os.environ.get("BOOKING_URL", DEFAULT_BOOKING_URL)

# Unset by default — lead delivery no-ops (logs only) until a real webhook target
# is configured, same pattern as BOOKING_URL's placeholder-until-configured approach.
LEAD_WEBHOOK_URL = os.environ.get("LEAD_WEBHOOK_URL")
