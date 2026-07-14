import unittest
from app import app
from utils.security import SecurityHelper
from models.db_models import HospitalModel

class TestAuth(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_password_hashing(self):
        pwd = "TestSecurePassword123"
        hash_val = SecurityHelper.hash_password(pwd)
        self.assertTrue(SecurityHelper.verify_password(hash_val, pwd))
        self.assertFalse(SecurityHelper.verify_password(hash_val, "WrongPassword"))

    def test_mobile_validation(self):
        self.assertTrue(SecurityHelper.validate_mobile("1234567890"))
        self.assertTrue(SecurityHelper.validate_mobile("+123456789012"))
        self.assertFalse(SecurityHelper.validate_mobile("123"))
        self.assertFalse(SecurityHelper.validate_mobile("abc1234567"))

    def test_login_page_renders(self):
        response = self.app.get('/login')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Access Portal', response.data)

    def test_unauthorized_redirect(self):
        # Accessing dashboard without log in should redirect to login page
        response = self.app.get('/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.location)

if __name__ == '__main__':
    unittest.main()
