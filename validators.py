# validators.py
from typing import Optional
from datetime import datetime

def validate_bet_amount(amount: float, min_bet: float, max_bet: float) -> Optional[str]:
    if amount < min_bet:
        return f"Minimum bet is {min_bet}"
    if amount > max_bet:
        return f"Maximum bet is {max_bet}"
    if not isinstance(amount, (int, float)):
        return "Amount must be a number"
    return None