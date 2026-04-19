"""Bootstrap package — app composition helpers extracted from app.py.

Each module owns one concern so create_app() reads as a sequence of
`init_x(app)` calls instead of a 200-line god function. This also lets
the test suite mock or skip individual concerns (e.g. scheduler) cleanly.
"""
