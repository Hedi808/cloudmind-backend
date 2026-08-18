from __future__ import annotations

import unittest

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.auth import hash_password, verify_password
from app.main import app
from app.schemas.auth import RegisterRequest


class AuthenticationTests(unittest.TestCase):
    def test_passwords_are_hashed_and_verified_with_argon2(self) -> None:
        encoded = hash_password("CloudMind123")

        self.assertNotEqual("CloudMind123", encoded)
        self.assertTrue(encoded.startswith("$argon2"))
        self.assertTrue(verify_password("CloudMind123", encoded))
        self.assertFalse(verify_password("WrongPassword123", encoded))

    def test_registration_normalizes_email_and_validates_password(self) -> None:
        request = RegisterRequest(
            display_name="  Ada   Lovelace  ",
            email=" ADA@Example.COM ",
            password="CloudMind123",
        )

        self.assertEqual("Ada Lovelace", request.display_name)
        self.assertEqual("ada@example.com", request.email)

        with self.assertRaises(ValidationError):
            RegisterRequest(
                display_name="Ada Lovelace",
                email="ada@example.com",
                password="letters-only",
            )

    def test_public_and_protected_route_boundaries(self) -> None:
        client = TestClient(app)

        self.assertEqual(200, client.get("/health").status_code)
        self.assertEqual(200, client.get("/api/auth/config").status_code)
        self.assertEqual(401, client.get("/api/projects").status_code)
        self.assertEqual(401, client.post("/api/chat/", json={"message": "hello"}).status_code)


if __name__ == "__main__":
    unittest.main()
