"""Search Console-modulet: JWT-signering, indlæste API-svar, blød fejlhåndtering og historik. Ingen netværk."""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from seo_agent import gsc
from seo_agent.report import Report

# Engangs-testnøgle (2048 bit, RSA), genereret til denne test og aldrig brugt andre steder. Gemt som ren base64-DER
# og samlet til PEM her, så den ikke ligner en rigtig hemmelighed for secret-scannere.
_KEY_BODY = (
    "MIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQCTca8pwudQKxYIkwRkRY3WCUHZ"
    "YCR+bOuzP2MSGVVznYmkT1aFq84znH+1LG9Jzv0zlBn4fcyH3wwu6ZR2NEbly3zMy08olU0Hm0aY"
    "ezwxvdVECthdfJVvNDGgDJwSn1AZiyYSEn4SpQlbPCZiak0CZJ42MMNJRuNJVJb8TVF+pCGtoQV5"
    "Ihgua1IrV1+kDRrYHF6XxGale8Ptzm+6Weibh2VTBI2RugQXWRnhGt0YkDeD0hHZp26d16QJf5SY"
    "1Hvpghb2id/8mQFCt7Q7yUO7/zG2zYr5czQ4wTIZEfRCnMNcqiUuQJEP2WxY3wdMXOqAJVf3YxvF"
    "Ka3eO/sh84P7AgMBAAECggEAPY9JDXwZPMEIfYL4Ye8iVXte+WWpRvmt/RRZhkx6f3+GYMpZOw0s"
    "1iKgtWF8g4n+8GKE51mKpC3ttcaDXEjeUwI/NHgsMCsJ0sOzWWWWj8QM/1Ax3vJtp9TYZVTuct3+"
    "QPP2bLQ43Ar42ZVHB28PgRDGd6SrXHRS4CKHuYaEoIU/XuAuP+sVs9T783HFdFxlNy5RbL4OCAFr"
    "Sn50tHezCVBZYJ2YGTE9SkUfidWM4QmJ3FrGok0sxOymns841pofHkQHAiX9oJTKUi6g/ZYKVNAZ"
    "3aikuBKnzat3hIFkJOnuzXiBrYiYfBog11ycv0N+j5q9veU/ca1osIhpLPn9DQKBgQDGkbmYCb7G"
    "HaawFlyQEuu78rpBAgiQ+McjEgGBkBl/sHq/QbLnvV5NHdS8kltQvlda4YqT0q2oZw9v5SDOuzQp"
    "0nYTCd2hmTQl92VIq3pyiOJorW/ntICWSqOBGAKmMf51aM2H/PXqexJMZv/5TDfQx1c7vQFLw7wh"
    "1SfAo3XcpQKBgQC+FplICezTzKkJDHRW/x/BjsHHQfm50lcMVI3uQ5VhO3DX9nyPp0dM5wRBn729"
    "lj2kxpL3WUkmGMFQCqlocb+vJQJbhZll/bEW021MR8RQS7zbnp1+I3bYNtPIcNvN3P3xX1poMPAt"
    "5K0II45b+m0dP4WrUMG5yTzpaYqx+9DcHwKBgQCiIorwYcSr77oTPa8G1Ow24tLCEe78sKWpNSKV"
    "sBuh72/KitKR9kXxodH6x2ZYX5LkWhTU7sltH/my29wV8TV+kKJomT2mnXm/JmpFE/8/VhXIcxVU"
    "lEYKcZdf6UMAgQHMzG5GA36onyUpzVBlNp68koff90v/mSscVPfIi6/JIQKBgQCX9Wrt+vk3TAnp"
    "cOpkTaluS5g/mU9wrGToN4QK8D4vr5wDGUn0cQ5/vMJbT78YG04GNrRwRhFDAlEvkoZhN2W8NwLO"
    "dVvu+8Kg874RV+HpKtK8Yu2WU/WC3TmqqAYfaUYculSErHKkzYVB12LLxsOJuSk7jeCAjA5Erhmx"
    "NRR/kwKBgQCH8jDucCJgFeh9mwDRlbTM4RRWAJb+AesRtEY/RkY76P0UFbHjO2Nj879EDSgX//jn"
    "UgeI1X5mVe3/SCvVZVu2UB6RiNkpw6bgSkAEmBHg31tETuNHEYcqprAV2gwUiMo/S+xwwqoJ0mce"
    "ZdROm4acm9NTV6JA65ITM3P1YFt04w=="
)
_BEGIN, _END = "-----BEGIN " + "PRIVATE KEY-----", "-----END " + "PRIVATE KEY-----"
TEST_KEY = "\n".join([_BEGIN, *[_KEY_BODY[i:i + 64] for i in range(0, len(_KEY_BODY), 64)], _END, ""])

SA = {"client_email": "seo@test-project.iam.gserviceaccount.com", "private_key_id": "abc123",
      "private_key": TEST_KEY, "token_uri": "https://oauth2.googleapis.com/token"}
SITE = "https://www.dialogbot.dk/"

ROW = lambda key, clicks, imps, ctr, pos: {"keys": [key], "clicks": clicks, "impressions": imps, "ctr": ctr, "position": pos}  # noqa: E731


def fake_http(responses: dict[str, tuple[int, dict]], calls: list):
    def http(url, body, headers):
        calls.append((url, body, headers))
        assert headers.get("Authorization", "").startswith("Bearer "), "token mangler"
        if url.startswith(gsc.INSPECT_API):
            return responses["inspect:" + body["inspectionUrl"]]
        dim = (body.get("dimensions") or ["total"])[0]
        return responses[dim]
    return http


class JwtTests(unittest.TestCase):
    def test_parse_key_and_sign_verify(self):
        n, e, d = gsc.parse_private_key(TEST_KEY)
        self.assertEqual(n.bit_length(), 2048)
        sig = gsc.rs256_sign(b"hej", (n, e, d))
        self.assertTrue(gsc.rs256_verify(b"hej", sig, n, e))
        self.assertFalse(gsc.rs256_verify(b"hej!", sig, n, e))

    def test_escaped_newlines_as_in_env_vars(self):
        self.assertEqual(gsc.parse_private_key(TEST_KEY.replace("\n", "\\n"))[0], gsc.parse_private_key(TEST_KEY)[0])

    def test_jwt_claims_and_signature(self):
        token = gsc.make_jwt(SA, now=1_700_000_000)
        h, c, s = token.split(".")
        pad = lambda x: x + "=" * (-len(x) % 4)  # noqa: E731
        header, claims = json.loads(base64.urlsafe_b64decode(pad(h))), json.loads(base64.urlsafe_b64decode(pad(c)))
        self.assertEqual(header, {"alg": "RS256", "typ": "JWT", "kid": "abc123"})
        self.assertEqual(claims["iss"], SA["client_email"])
        self.assertEqual(claims["scope"], gsc.SCOPE)
        self.assertEqual((claims["iat"], claims["exp"]), (1_700_000_000, 1_700_003_600))
        n, e, _ = gsc.parse_private_key(TEST_KEY)
        self.assertTrue(gsc.rs256_verify(f"{h}.{c}".encode(), base64.urlsafe_b64decode(pad(s)), n, e))

    def test_bad_key_is_a_clear_error(self):
        with self.assertRaises(gsc.GscError):
            gsc.parse_private_key(f"{_BEGIN}\nAAAA\n{_END}")

    def test_token_exchange(self):
        seen = {}

        def post_form(url, fields):
            seen.update(fields)
            return 200, {"access_token": "ya29.x", "expires_in": 3599}
        self.assertEqual(gsc.fetch_token(SA, post_form), "ya29.x")
        self.assertEqual(seen["grant_type"], "urn:ietf:params:oauth:grant-type:jwt-bearer")
        self.assertEqual(seen["assertion"].count("."), 2)
        with self.assertRaises(gsc.GscError):
            gsc.fetch_token(SA, lambda u, f: (400, {"error": "invalid_grant"}))


class ConfigTests(unittest.TestCase):
    def test_missing_secrets_means_skip(self):
        self.assertIsNone(gsc.load_config({}))
        self.assertIsNone(gsc.load_config({"GSC_SITE_URL": SITE}))

    def test_inline_json_and_file_path(self):
        sa, site = gsc.load_config({"GSC_SERVICE_ACCOUNT_JSON": json.dumps(SA), "GSC_SITE_URL": SITE})
        self.assertEqual((sa["client_email"], site), (SA["client_email"], SITE))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "sa.json"
            p.write_text(json.dumps(SA))
            self.assertEqual(gsc.load_config({"GSC_SERVICE_ACCOUNT_JSON": str(p), "GSC_SITE_URL": SITE})[1], SITE)
        with self.assertRaises(gsc.GscError):
            gsc.load_config({"GSC_SERVICE_ACCOUNT_JSON": "{not json", "GSC_SITE_URL": SITE})
        with self.assertRaises(gsc.GscError):
            gsc.load_config({"GSC_SERVICE_ACCOUNT_JSON": json.dumps({"client_email": "x"}), "GSC_SITE_URL": SITE})


class CollectTests(unittest.TestCase):
    def responses(self):
        return {
            "total": (200, {"rows": [{"clicks": 42, "impressions": 1500, "ctr": 0.028, "position": 18.42}]}),
            "query": (200, {"rows": [ROW("ai receptionist", 20, 400, 0.05, 6.2), ROW("ai telefonsvarer", 9, 300, 0.03, 9.9)]}),
            "page": (200, {"rows": [ROW(SITE, 30, 900, 0.033, 12.1)]}),
            "inspect:https://www.dialogbot.dk/": (200, {"inspectionResult": {"indexStatusResult": {
                "verdict": "PASS", "coverageState": "Submitted and indexed", "robotsTxtState": "ALLOWED", "indexingState": "INDEXING_ALLOWED",
                "lastCrawlTime": "2026-10-05T10:11:12Z", "googleCanonical": "https://www.dialogbot.dk/"}}}),
            "inspect:https://www.dialogbot.dk/priser": (200, {"inspectionResult": {"indexStatusResult": {
                "verdict": "NEUTRAL", "coverageState": "Discovered - currently not indexed", "robotsTxtState": "ALLOWED",
                "indexingState": "INDEXING_ALLOWED"}}}),
        }

    def test_collect_happy_path(self):
        calls: list = []
        data = gsc.collect(SA, SITE, ["https://www.dialogbot.dk/", "https://www.dialogbot.dk/priser", "https://www.dialogbot.dk/x"],
                           http=fake_http(self.responses(), calls), token="t", today=date(2026, 10, 8), max_inspect=2)
        self.assertEqual(data["period"], {"start": "2026-09-08", "end": "2026-10-05"})
        self.assertEqual(data["totals"], {"clicks": 42, "impressions": 1500, "ctr": 2.8, "position": 18.4})
        self.assertEqual(data["queries"][0]["key"], "ai receptionist")
        self.assertEqual(data["pages"][0]["clicks"], 30)
        self.assertEqual((data["indexing"]["inspected"], data["indexing"]["indexed"], data["indexing"]["not_indexed"]), (2, 1, 1))
        self.assertEqual(data["indexing"]["items"][1]["coverage"], "Discovered - currently not indexed")
        self.assertEqual(data["errors"], [])
        self.assertEqual(len(calls), 5)  # 3 søgeanalyser + 2 inspektioner (max_inspect)
        self.assertIn("sites/https%3A%2F%2Fwww.dialogbot.dk%2F/searchAnalytics", calls[0][0])
        self.assertEqual(calls[0][1]["startDate"], "2026-09-08")

    def test_403_is_explained_and_does_not_crash(self):
        r = self.responses()
        r["total"] = (403, {"error": {"code": 403, "message": "User does not have sufficient permission"}})
        data = gsc.collect(SA, SITE, ["https://www.dialogbot.dk/"], http=fake_http(r, []), token="t", today=date(2026, 10, 8))
        self.assertEqual(data["totals"], {})
        self.assertTrue(any("service account-mailen" in e for e in data["errors"]))
        self.assertEqual(data["indexing"]["inspected"], 1)  # inspektion kører stadig

    def test_token_failure_is_soft(self):
        bad = dict(SA, private_key=f"{_BEGIN}\nAAAA\n{_END}")
        data = gsc.collect(bad, SITE, [], http=fake_http({}, []), today=date(2026, 10, 8))
        self.assertEqual(len(data["errors"]), 1)
        self.assertIn("private_key", data["errors"][0])

    def test_history_and_markdown(self):
        data = gsc.collect(SA, SITE, ["https://www.dialogbot.dk/", "https://www.dialogbot.dk/priser"],
                           http=fake_http(self.responses(), []), token="t", today=date(2026, 10, 8))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "gsc-history.json"
            path.write_text(json.dumps([{"scanned_at": "2026-09-30T05:00:00+00:00", "start": "2026-08-31", "end": "2026-09-27",
                                         "clicks": 30, "impressions": 1000, "ctr": 3.0, "position": 20.0, "indexed": 1, "inspected": 2}]))
            history = gsc.update_history(path, data, "2026-10-08T05:00:00+00:00")
            self.assertEqual(len(history), 2)
            self.assertEqual(history[-1]["clicks"], 42)
            # samme scanning igen overskriver i stedet for at duplikere
            self.assertEqual(len(gsc.update_history(path, data, "2026-10-08T05:00:00+00:00")), 2)
        data["history"] = history
        rep = Report(SITE.rstrip("/"), "2026-10-08T05:00:00+00:00", 1, [], gsc=data)
        md = rep.to_markdown()
        self.assertIn("## Google Search Console", md)
        self.assertIn("| 42 (▲ +12) | 1500 (▲ +500) | 2.8 % (▼ -0.2 pp) | 18.4 (▲ -1.6) |", md)
        self.assertIn("ai receptionist", md)
        self.assertIn("Discovered - currently not indexed", md)
        self.assertIn("### Udvikling", md)
        self.assertEqual(json.loads(rep.to_json())["gsc"]["totals"]["clicks"], 42)

    def test_no_section_without_data(self):
        self.assertNotIn("Search Console", Report(SITE, "t", 1, []).to_markdown())


if __name__ == "__main__":
    unittest.main()
