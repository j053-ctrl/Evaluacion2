"""Carga variables locales desde .env sin sobrescribir el entorno del sistema."""

import os
from pathlib import Path


def load_environment(env_file=None):
    path = Path(env_file) if env_file else Path(__file__).resolve().parent.parent / '.env'
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        name, value = line.split('=', 1)
        name = name.strip()
        value = value.strip()
        if value[:1] in {'"', "'"} and value[-1:] == value[:1]:
            value = value[1:-1]
        if name:
            os.environ.setdefault(name, value)

