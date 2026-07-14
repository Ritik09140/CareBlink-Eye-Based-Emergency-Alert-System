import unittest
import json
from app import app
from database.connection import db

class TestAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.testing = True

    def test_get_patient_threshold(self):
        # PT-2045 was seeded in init_db
        response = self.client.get('/api/patient/PT-2045/threshold')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("ear_threshold"), 0.22)
        self.assertEqual(data.get("baseline_ear"), 0.28)

    def test_nonexistent_patient_threshold(self):
        response = self.client.get('/api/patient/NONEXISTENT/threshold')
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertFalse(data.get("success"))

    def test_unauthorized_api_calls(self):
        # Verify JSON endpoints return 401 instead of redirecting when unauthorized
        for url in ['/api/camera/status', '/api/alerts/active', '/api/hospital/records']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 401)
            data = json.loads(response.data)
            self.assertFalse(data.get("success"))
            self.assertIn("Unauthorized", data.get("message"))

if __name__ == '__main__':
    unittest.main()
