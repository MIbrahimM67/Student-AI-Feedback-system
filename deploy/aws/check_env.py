"""Validate deployment prerequisites without printing secrets or executing .env."""
import re
import sys
from pathlib import Path


def validate(path):
    values = {}
    errors = []
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            errors.append(f'Line {number}: expected KEY=value; multiline values are unsupported')
            continue
        key, value = line.split('=', 1)
        value = value.strip()
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                errors.append(f'Line {number}: unmatched quote')
                continue
            value = value[1:-1]
        values[key.strip()] = value
    required = ('POSTGRES_PASSWORD', 'APP_USER_PASSWORD', 'API_DOMAIN', 'TLS_EMAIL',
                'GRADIENT_API_KEY', 'FIREBASE_PROJECT_ID', 'FIREBASE_CLIENT_EMAIL',
                'FIREBASE_PRIVATE_KEY', 'FIREBASE_STORAGE_BUCKET')
    for key in required:
        if not values.get(key):
            errors.append(f'{key} is required')
    for key in ('POSTGRES_PASSWORD', 'APP_USER_PASSWORD'):
        if not re.fullmatch(r'[0-9a-fA-F]{64}', values.get(key, '')):
            errors.append(f'{key} must be 64 hex characters (openssl rand -hex 32)')
    if values.get('POSTGRES_PASSWORD') == values.get('APP_USER_PASSWORD'):
        errors.append('Database owner and application passwords must differ')
    domain = values.get('API_DOMAIN', '')
    if not re.fullmatch(r'(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}', domain):
        errors.append('API_DOMAIN must be a DNS hostname, without scheme, path, or port')
    if values.get('DEBUG', 'false').lower() != 'false' or values.get('USE_MOCKS', 'false').lower() != 'false':
        errors.append('DEBUG and USE_MOCKS must be false')
    if values.get('FRONTEND_URL') != 'https://student-ai-feedback-system.vercel.app':
        errors.append('FRONTEND_URL must match the current production frontend; review CORS before changing it')
    if values.get('FIREBASE_PRIVATE_KEY') and 'BEGIN PRIVATE KEY' not in values['FIREBASE_PRIVATE_KEY']:
        errors.append('FIREBASE_PRIVATE_KEY must contain the PEM private key')
    return errors


if __name__ == '__main__':
    try:
        errors = validate(sys.argv[1] if len(sys.argv) > 1 else '.env.aws')
    except OSError:
        sys.exit('Environment file is missing or unreadable')
    if errors:
        sys.exit('\n'.join(errors))
    print('Deployment environment checks passed (credentials still require live verification).')
