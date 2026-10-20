"""Validation conditions must remain active with Python optimization enabled."""


def require(condition, message=lambda: 'Hardware validation failed'):
    """Keep the existing AssertionError API and evaluate failure detail lazily."""
    if not condition:
        raise AssertionError(message())
