from copy import deepcopy

# Stands in for the user ID of an authenticated session.
CURRENT_USER_ID = "user_123"

APPROVAL_LIMIT = 499
REFUND_WINDOW_DAYS = 7

USERS = {
    "user_123": {
        "name": "Rahul",
        "plan": "Pro",
        "plan_amount": 999,
        "recharges": [
            {
                "recharge_id": "rch_456",
                "recharge_amount": 999,
                "recharge_status": "completed",
                "recharge_age_days": 2,
                "refund_status": "not_refunded",
            },
            {
                "recharge_id": "rch_457",
                "recharge_amount": 499,
                "recharge_status": "completed",
                "recharge_age_days": 1,
                "refund_status": "not_refunded",
            },
        ],
    }
}


class RefundStore:
    """Simulated account database; each chat session gets its own copy."""

    def __init__(self, users=None):
        self.users = deepcopy(USERS if users is None else users)
        self.refunds = []
        self.support_requests = []
