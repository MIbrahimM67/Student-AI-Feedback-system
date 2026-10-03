-- psql reads the container environment explicitly. SQL current_setting() does not.
-- Also run after restoring a backup, using the database owner's credentials.
\getenv app_password APP_USER_PASSWORD
ALTER ROLE app_user WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD :'app_password';

-- App sessions deliberately cannot ALTER tables owned by the database owner.
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'free';
ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status TEXT DEFAULT 'inactive';
ALTER TABLE users ADD COLUMN IF NOT EXISTS current_period_end TIMESTAMPTZ;
