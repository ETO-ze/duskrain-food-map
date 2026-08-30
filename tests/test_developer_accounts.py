import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

import app


class DeveloperAccountFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.original_data_dir = app.DATA_DIR
        self.original_db_path = app.DB_PATH
        self.original_avatar_dir = app.AVATAR_DIR
        self.original_smtp_configured = app.smtp_configured
        self.original_send_activation = app.send_activation_email
        self.original_send_reset = app.send_password_reset_email
        app.DATA_DIR = self.data_dir
        app.DB_PATH = self.data_dir / "food_map.db"
        app.AVATAR_DIR = self.data_dir / "avatars"
        app.AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        app.init_db()
        self.tokens: dict[str, str] = {}
        app.smtp_configured = lambda: True
        app.send_activation_email = lambda account, token: self.tokens.update(activation=token)
        app.send_password_reset_email = lambda account, token: self.tokens.update(reset=token)
        self.client = TestClient(app.app, base_url="https://duskrain.cn")
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        app.DATA_DIR = self.original_data_dir
        app.DB_PATH = self.original_db_path
        app.AVATAR_DIR = self.original_avatar_dir
        app.smtp_configured = self.original_smtp_configured
        app.send_activation_email = self.original_send_activation
        app.send_password_reset_email = self.original_send_reset
        self.temp_dir.cleanup()

    def invite_and_activate(self) -> tuple[int, dict]:
        invitation = self.client.post(
            "/food-map/api/admin/authors",
            json={"author_name": "Test Writer", "email": "writer@example.com"},
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)
        account_id = invitation.json()["id"]
        activation = self.client.post(
            "/food-map/api/developer/activation/complete",
            json={
                "token": self.tokens["activation"],
                "username": "test.writer",
                "password": "password8",
            },
        )
        self.assertEqual(activation.status_code, 200, activation.text)
        return account_id, activation.json()

    def test_invitation_is_one_time_and_creates_no_shared_password(self) -> None:
        account_id, account = self.invite_and_activate()
        self.assertEqual(account["account_status"], "active")
        reused = self.client.post(
            "/food-map/api/developer/activation/complete",
            json={
                "token": self.tokens["activation"],
                "username": "another.writer",
                "password": "password8",
            },
        )
        self.assertEqual(reused.status_code, 400)
        conn = sqlite3.connect(app.DB_PATH)
        try:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM developer_accounts WHERE id = ?", (account_id,)).fetchone()
            self.assertEqual(row["password_algorithm"], "argon2id")
            self.assertFalse(app.account_password_matches(row, app.INITIAL_DEVELOPER_PASSWORD))
        finally:
            conn.close()

    def test_owner_account_survives_author_rename(self) -> None:
        account_id, _ = self.invite_and_activate()
        created = self.client.post(
            "/food-map/api/developer/places",
            json={"name": "Test Place", "lng": 121.1, "lat": 31.1, "rating_author": "spoofed"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        renamed = self.client.put(
            f"/food-map/api/admin/authors/{account_id}",
            json={"author_name": "Renamed Writer", "email": "writer@example.com", "is_active": True},
        )
        self.assertEqual(renamed.status_code, 200, renamed.text)
        places = self.client.get("/food-map/api/developer/places")
        self.assertEqual(places.status_code, 200)
        self.assertEqual(len(places.json()), 1)
        self.assertEqual(places.json()[0]["rating_author"], "Renamed Writer")
        conn = sqlite3.connect(app.DB_PATH)
        try:
            owner_id = conn.execute(
                "SELECT owner_account_id FROM food_places WHERE id = ?", (created.json()["id"],)
            ).fetchone()[0]
            self.assertEqual(owner_id, account_id)
        finally:
            conn.close()

    def test_avatar_and_email_password_reset(self) -> None:
        _, _ = self.invite_and_activate()
        image = Image.new("RGB", (32, 32), (20, 110, 160))
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        uploaded = self.client.post(
            "/food-map/api/developer/avatar",
            files={"avatar": ("avatar.png", buffer.getvalue(), "image/png")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertTrue(uploaded.json()["avatar_url"].endswith(".webp"))

        admin_reset = self.client.post(
            f"/food-map/api/admin/authors/{uploaded.json()['id']}/reset-password"
        )
        self.assertEqual(admin_reset.status_code, 200, admin_reset.text)
        reset = self.client.post(
            "/food-map/api/developer/password/reset",
            json={"token": self.tokens["reset"], "password": "newpassword8"},
        )
        self.assertEqual(reset.status_code, 200, reset.text)
        self.assertEqual(self.client.get("/food-map/api/developer/session").status_code, 401)
        login = self.client.post(
            "/food-map/api/developer/login",
            json={"login": "writer@example.com", "password": "newpassword8"},
        )
        self.assertEqual(login.status_code, 200, login.text)

    def test_oauth_avatar_imports_once_and_preserves_manual_avatar(self) -> None:
        account_id, _ = self.invite_and_activate()
        image = Image.new("RGB", (40, 40), (35, 120, 180))
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        original_download = app.download_oauth_avatar
        app.download_oauth_avatar = lambda provider, url: buffer.getvalue()
        try:
            self.assertTrue(app.maybe_import_oauth_avatar(
                account_id, "google", "https://lh3.googleusercontent.com/example"
            ))
            imported = self.client.get("/food-map/api/developer/session").json()["avatar_url"]
            self.assertTrue(imported.endswith(".webp"))

            manual = Image.new("RGB", (32, 32), (180, 70, 45))
            manual_buffer = io.BytesIO()
            manual.save(manual_buffer, "PNG")
            uploaded = self.client.post(
                "/food-map/api/developer/avatar",
                files={"avatar": ("manual.png", manual_buffer.getvalue(), "image/png")},
            )
            self.assertEqual(uploaded.status_code, 200, uploaded.text)
            manual_url = uploaded.json()["avatar_url"]
            self.assertFalse(app.maybe_import_oauth_avatar(
                account_id, "github", "https://avatars.githubusercontent.com/u/1"
            ))
            self.assertEqual(
                self.client.get("/food-map/api/developer/session").json()["avatar_url"],
                manual_url,
            )
        finally:
            app.download_oauth_avatar = original_download

    def test_oauth_avatar_hosts_and_phone_capability_are_restricted(self) -> None:
        self.assertTrue(app.oauth_avatar_url_allowed(
            "google", "https://lh3.googleusercontent.com/avatar"
        ))
        self.assertTrue(app.oauth_avatar_url_allowed(
            "github", "https://avatars.githubusercontent.com/u/1"
        ))
        self.assertFalse(app.oauth_avatar_url_allowed(
            "github", "https://example.com/avatar.png"
        ))
        config = self.client.get("/food-map/api/developer/auth/config")
        self.assertEqual(config.status_code, 200, config.text)
        self.assertEqual(
            config.json()["identity_capabilities"][app.PHONE_IDENTITY_PROVIDER],
            app.PHONE_LOGIN_ENABLED,
        )

    def test_activation_email_escapes_author_name(self) -> None:
        captured: dict[str, str] = {}
        original_sender = app.send_account_email
        app.send_account_email = lambda recipient, subject, text, html_body: captured.update(
            recipient=recipient,
            subject=subject,
            text=text,
            html=html_body,
        )
        try:
            self.original_send_activation(
                {"author_name": "Writer <Test>", "email": "writer@example.com", "username": "adminnailong"},
                "one-time-token",
            )
        finally:
            app.send_account_email = original_sender
        self.assertEqual(captured["recipient"], "writer@example.com")
        self.assertIn("Writer &lt;Test&gt;", captured["html"])
        self.assertNotIn("Writer <Test>", captured["html"])
        self.assertIn("验证邮箱并激活账户", captured["html"])
        self.assertIn("https://duskrain.cn/black-hole/assets/logo.webp", captured["html"])
        self.assertIn("https://duskrain.cn/#about", captured["html"])
        self.assertIn("https://duskrain.cn/privacy/", captured["html"])
        self.assertIn("https://duskrain.cn/terms/", captured["html"])
        self.assertIn("adminnailong", captured["html"])

    def test_existing_account_activation_preserves_username_suggestion(self) -> None:
        account_id, _ = self.invite_and_activate()
        resent = self.client.post(f"/food-map/api/admin/authors/{account_id}/send-invitation")
        self.assertEqual(resent.status_code, 200, resent.text)
        inspected = self.client.post(
            "/food-map/api/developer/activation/inspect",
            json={"token": self.tokens["activation"]},
        )
        self.assertEqual(inspected.status_code, 200, inspected.text)
        self.assertTrue(inspected.json()["existing_username"])
        self.assertEqual(inspected.json()["username"], "test.writer")

    def test_new_account_activation_leaves_username_empty(self) -> None:
        invitation = self.client.post(
            "/food-map/api/admin/authors",
            json={"author_name": "New Writer", "email": "new.writer@example.com"},
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)
        inspected = self.client.post(
            "/food-map/api/developer/activation/inspect",
            json={"token": self.tokens["activation"]},
        )
        self.assertEqual(inspected.status_code, 200, inspected.text)
        self.assertFalse(inspected.json()["existing_username"])
        self.assertEqual(inspected.json()["username"], "")

    def test_admin_can_delete_empty_author_with_exact_confirmation(self) -> None:
        invitation = self.client.post(
            "/food-map/api/admin/authors",
            json={"author_name": "Unused Writer", "email": "unused@example.com"},
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)
        account_id = invitation.json()["id"]
        mismatch = self.client.request(
            "DELETE",
            f"/food-map/api/admin/authors/{account_id}",
            json={"author_name": "Wrong Writer"},
        )
        self.assertEqual(mismatch.status_code, 400, mismatch.text)
        deleted = self.client.request(
            "DELETE",
            f"/food-map/api/admin/authors/{account_id}",
            json={"author_name": "Unused Writer"},
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertTrue(deleted.json()["deleted"])
        conn = sqlite3.connect(app.DB_PATH)
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM developer_accounts WHERE id = ?", (account_id,)).fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM developer_invitations WHERE account_id = ?", (account_id,)).fetchone()[0],
                0,
            )
        finally:
            conn.close()

    def test_admin_cannot_delete_author_with_places(self) -> None:
        account_id, _ = self.invite_and_activate()
        created = self.client.post(
            "/food-map/api/developer/places",
            json={"name": "Protected Place", "lng": 121.2, "lat": 31.2},
        )
        self.assertEqual(created.status_code, 200, created.text)
        blocked = self.client.request(
            "DELETE",
            f"/food-map/api/admin/authors/{account_id}",
            json={"author_name": "Test Writer"},
        )
        self.assertEqual(blocked.status_code, 409, blocked.text)
        self.assertIn("1 家店", blocked.json()["detail"])
        conn = sqlite3.connect(app.DB_PATH)
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM developer_accounts WHERE id = ?", (account_id,)).fetchone()[0],
                1,
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
