import tempfile
import unittest
from pathlib import Path
from check_env import validate


class DeploymentEnvironmentTests(unittest.TestCase):
    def check(self, overrides=None):
        values = dict(POSTGRES_PASSWORD='a' * 64, APP_USER_PASSWORD='b' * 64,
                      API_DOMAIN='api.example.com', TLS_EMAIL='operator@example.com',
                      GRADIENT_API_KEY='example-test-key', FIREBASE_PROJECT_ID='example',
                      FIREBASE_CLIENT_EMAIL='example@example.iam.gserviceaccount.com',
                      FIREBASE_PRIVATE_KEY='"-----BEGIN PRIVATE KEY-----\\nTEST\\n-----END PRIVATE KEY-----\\n"',
                      FIREBASE_STORAGE_BUCKET='example.firebasestorage.app',
                      FRONTEND_URL='https://student-ai-feedback-system.vercel.app')
        values.update(overrides or {})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env.aws'
            path.write_text('\n'.join(f'{k}={v}' for k, v in values.items()))
            return validate(path)

    def test_valid_config(self):
        self.assertEqual(self.check(), [])

    def test_placeholder_credentials_and_password_reuse_rejected(self):
        errors = self.check({'APP_USER_PASSWORD': 'a' * 64, 'GRADIENT_API_KEY': ''})
        self.assertTrue(any('must differ' in e for e in errors))
        self.assertTrue(any('GRADIENT_API_KEY' in e for e in errors))

    def test_unsafe_database_url_password_rejected_without_disclosure(self):
        secret = 'private@password/with:characters'
        errors = self.check({'APP_USER_PASSWORD': secret})
        self.assertTrue(any('64 hex' in e for e in errors))
        self.assertNotIn(secret, str(errors))

    def test_public_debug_and_mock_modes_rejected(self):
        self.assertTrue(self.check({'DEBUG': 'true'}))
        self.assertTrue(self.check({'USE_MOCKS': 'true'}))

    def test_scheme_path_and_caddy_injection_rejected(self):
        for domain in ('https://api.example.com', 'api.example.com/x', ':80', 'api.example.com {'):
            with self.subTest(domain=domain):
                self.assertTrue(self.check({'API_DOMAIN': domain}))


if __name__ == '__main__':
    unittest.main()
