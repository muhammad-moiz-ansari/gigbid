"""Per-user OAuth tokens, encrypted at rest with a key from the environment and never logged."""
import json

from cryptography.fernet import Fernet

from apps.api.config import settings
from apps.api.db import get_record, put_record, transaction


def _cipher():
    if not settings().token_encryption_key:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY is not configured")
    return Fernet(settings().token_encryption_key.encode())


def save_tokens(tenant, provider, tokens):
    sealed = _cipher().encrypt(json.dumps(tokens).encode()).decode()
    with transaction() as db:
        put_record(db, tenant, "oauth_token", provider, {"sealed": sealed})


def load_tokens(tenant, provider):
    with transaction() as db:
        record = get_record(db, tenant, "oauth_token", provider)
        sealed = record.value["sealed"] if record else None
    return json.loads(_cipher().decrypt(sealed.encode())) if sealed else None


def delete_tokens(tenant, provider):
    with transaction() as db:
        record = get_record(db, tenant, "oauth_token", provider)
        if record:
            db.delete(record)
