"""Atomic UTF-8 JSON snapshots."""
import json
import os
import re
import tempfile
from pathlib import Path


def save(database, filename):
    """Save an internal course-code index grouped by subject in JSON."""
    grouped = {}
    for code, course in database.items():
        match = re.fullmatch(r'([A-Z]+)\d+[A-Z]*', code)
        if not match:
            raise ValueError(f'Invalid course code: {code}')
        grouped.setdefault(match.group(1), {})[code] = course
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as stream:
            temp = stream.name
            json.dump(grouped, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
