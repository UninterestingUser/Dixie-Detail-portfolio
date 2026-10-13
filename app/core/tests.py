from unittest import mock

from django.db import OperationalError
from django.test import SimpleTestCase


@mock.patch("core.views.connection")
class HealthTests(SimpleTestCase):
    def test_ok_when_database_answers(self, connection):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_unavailable_when_database_fails(self, connection):
        connection.cursor.side_effect = OperationalError("down")
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})

    def test_rejects_post(self, connection):
        self.assertEqual(self.client.post("/health").status_code, 405)


@mock.patch("core.views.connection")
class PublicEntranceTests(SimpleTestCase):
    def test_public_entrance_reaches_health(self, connection):
        response = self.client.get("/health", headers={"X-Dixie-Entrance": "public"})
        self.assertEqual(response.status_code, 200)

    def test_public_entrance_blocks_other_paths(self, connection):
        for path in ("/admin/", "/api/private/", "/api/publicx", "/api/public/../../admin/"):
            with self.subTest(path=path):
                response = self.client.get(path, headers={"X-Dixie-Entrance": "public"})
                self.assertEqual(response.status_code, 404)

    def test_missing_header_counts_as_public(self, connection):
        self.assertEqual(self.client.get("/anything").status_code, 404)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_tailnet_entrance_reaches_everything(self, connection):
        # No such page yet, so Django's own 404 — but the middleware let it through.
        with mock.patch("core.middleware.HttpResponseNotFound") as blocked:
            self.client.get("/anything", headers={"X-Dixie-Entrance": "tailnet"})
        blocked.assert_not_called()
