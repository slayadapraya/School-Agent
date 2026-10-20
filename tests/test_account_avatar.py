"""Account pictures remain bounded, inert and owned by the signed-in account."""

import base64
import io
import unittest
from PIL import Image
from test_administration import Administration


class AccountAvatar(unittest.TestCase):
    setUp = Administration.setUp
    tearDown = Administration.tearDown
    request = Administration.request
    login = Administration.login

    def test_picture_is_reencoded_and_account_owned(self):
        user = self.login("student")
        other = self.login("other")
        image = io.BytesIO()
        Image.new("RGB", (300, 180), "green").save(image, "PNG")
        encoded = "data:image/png;base64," + base64.b64encode(image.getvalue()).decode()
        status, result, _ = self.request(
            "/api/preferences/avatar",
            {"image": encoded, "user_id": self.people["other"]["id"]},
            user,
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["image"].startswith("data:image/jpeg;base64,"))
        with Image.open(
            io.BytesIO(base64.b64decode(result["image"].split(",")[1]))
        ) as picture:
            self.assertEqual(picture.size, (128, 128))
            self.assertFalse(picture.getexif())
        self.assertEqual(
            self.request("/api/bootstrap", cookie=user)[1]["avatar"], result
        )
        self.assertEqual(
            self.request("/api/preferences/avatar", cookie=other)[1],
            {"image": "", "icon": ""},
        )
        self.assertEqual(
            self.request("/api/preferences/avatar", {"icon": "🌱"}, user)[1],
            {"image": "", "icon": "🌱"},
        )
        self.assertEqual(
            self.request("/api/preferences/avatar", {}, user)[1],
            {"image": "", "icon": ""},
        )

    def test_invalid_uploads_do_not_replace_picture(self):
        user = self.login("student")
        self.request("/api/preferences/avatar", {"icon": "⭐"}, user)
        for value in (
            {"image": "data:image/svg+xml;base64,PHN2Zy8+"},
            {"image": "data:image/png;base64,bm90LWFuLWltYWdl"},
            {"image": 1},
            {"icon": "<script>"},
            {"icon": "🌱", "image": "x"},
        ):
            self.assertEqual(
                self.request("/api/preferences/avatar", value, user)[0], 400
            )
        self.assertEqual(
            self.request("/api/preferences/avatar", cookie=user)[1]["icon"], "⭐"
        )
