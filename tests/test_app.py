import unittest
from types import SimpleNamespace
from unittest.mock import patch


with patch("google.cloud.datastore.Client"), patch("google.cloud.storage.Client"):
    import main


class AppStructureTests(unittest.TestCase):
    def setUp(self):
        self.client = main.app.test_client()

    def test_health_response(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "Tarpaulin API is running")

    def test_all_assignment_endpoints_are_registered(self):
        rules = [
            rule
            for rule in main.app.url_map.iter_rules()
            if rule.endpoint != "static" and rule.rule != "/"
        ]

        self.assertEqual(len(rules), 13)

    def test_bearer_token_is_extracted(self):
        request = SimpleNamespace(headers={"Authorization": "Bearer example-token"})

        self.assertEqual(main.get_token(request), "example-token")

    def test_missing_bearer_token_is_rejected(self):
        request = SimpleNamespace(headers={})

        with self.assertRaises(main.AuthError):
            main.get_token(request)


if __name__ == "__main__":
    unittest.main()
