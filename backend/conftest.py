# test_backend.py is a manual smoke script: it calls a running server (and GEE)
# at import time, so pytest must never collect it.
collect_ignore = ["test_backend.py"]
