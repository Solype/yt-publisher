"""Where the scripts find their keys."""
import os
import re


def env(key, default=None):
    """The variable, else the one of the nearest .env above this file that has it."""
    if os.environ.get(key):
        return os.environ[key]
    d = os.path.dirname(os.path.abspath(__file__))
    while d != os.path.dirname(d):
        d = os.path.dirname(d)
        if os.path.exists(f"{d}/.env"):
            with open(f"{d}/.env") as f:
                for line in f:
                    m = re.match(rf"(?:export )?{key}=(.*)$", line.strip())
                    if m:
                        return m[1].strip("'\"")
    return default
