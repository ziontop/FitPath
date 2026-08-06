"""Recommendation + plan-generation engine services.

These modules turn the read-only training spec in :mod:`app.training.params`
into concrete, user-scoped recommendations (programs, nutrition plans,
performance analytics). They are the algorithmic layer between the thin routers
under ``app/routes`` and the ORM models; every function takes a ``Session`` plus
the authenticated ``user_id`` and scopes its queries accordingly.
"""
