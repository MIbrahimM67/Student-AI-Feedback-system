-- Deployment owner applies this once; no API credentials are stored here.
CREATE TABLE IF NOT EXISTS provider_key_cooldowns (
    key_hash TEXT PRIMARY KEY,
    blocked_until TIMESTAMPTZ NOT NULL
);
REVOKE ALL ON provider_key_cooldowns FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE ON provider_key_cooldowns TO app_user;
