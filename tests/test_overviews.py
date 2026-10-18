import unittest
import json
from unittest.mock import patch, Mock
from app import research as r


class ResearchOverview(unittest.TestCase):
    def source(self):
        return {
            "id": "wiki-uc",
            "title": "University of Canterbury",
            "provider": "Wikipedia",
            "url": "https://en.wikipedia.org/?curid=42",
            "text": "The University of Canterbury is a public research university based in Christchurch, New Zealand. It was founded in 1873 as Canterbury College. It offers undergraduate and postgraduate study across a range of subjects.",
            "locator": "Wikipedia article",
        }

    def candidate(self):
        return {
            "answer": "The University of Canterbury is a public research university in Christchurch, New Zealand. It began in 1873 as Canterbury College and offers undergraduate and postgraduate study.",
            "source_ids": ["wiki-uc"],
        }

    def test_supported_overview_has_small_unverified_note(self):
        model = Mock(side_effect=[self.candidate(), {"allow": True, "supported": True}])
        with patch.object(r, "retrieve", return_value=([self.source()], [])):
            text, meta = r.respond(
                "University of Canterbury",
                False,
                model,
                "tell me a little about the University of Canterbury nz",
                allow_overview=True,
            )
        self.assertIn("Christchurch", text)
        self.assertEqual(meta["route"], "research_overview")
        self.assertFalse(meta["independently_verified"])
        self.assertIn("Not independently verified", meta["disclaimer"])

    def test_wrong_entity_does_not_become_an_overview(self):
        source = self.source()
        source["title"] = "Canterbury of New Zealand"
        source["text"] = (
            "Canterbury is a clothing brand. The University of Canterbury is a separate institution."
        )
        model = Mock(side_effect=AssertionError)
        with patch.object(r, "retrieve", return_value=([source], [])):
            text, meta = r.respond(
                "University of Canterbury",
                False,
                model,
                "tell me about the University of Canterbury",
                allow_overview=True,
            )
        self.assertEqual(meta["sources"], [])
        self.assertNotIn("clothing", text)
        model.assert_not_called()

    def test_review_rejects_unsupported_or_incomplete_verdict(self):
        for verdict in [
            {"allow": False, "supported": True},
            {"allow": True, "supported": False},
            {"allow": "true", "supported": True},
            {},
        ]:
            model = Mock(side_effect=[self.candidate(), verdict])
            self.assertIsNone(
                r.overview("tell me about Canterbury", [self.source()], [], model)
            )

    def test_fake_citations_and_model_urls_rejected(self):
        for bad in [
            {**self.candidate(), "source_ids": ["fake"]},
            {
                **self.candidate(),
                "answer": "Visit https://evil.example to solve all your assignments.",
            },
        ]:
            self.assertIsNone(
                r.overview(
                    "tell me about Canterbury", [self.source()], [], lambda *a: bad
                )
            )

    def test_assessment_requests_never_call_summary_model(self):
        for q in [
            "Write my essay about Canterbury",
            "Tell me about how to solve 2x = 17",
            "Give the final answer to this homework",
        ]:
            model = Mock(side_effect=AssertionError)
            self.assertIsNone(r.overview(q, [self.source()], [], model))
            model.assert_not_called()

    def test_overview_is_explicitly_configured(self):
        model = Mock(return_value={"answers_question": False})
        with patch.object(r, "retrieve", return_value=([self.source()], [])):
            _, meta = r.respond(
                "University of Canterbury",
                False,
                model,
                "tell me about the University of Canterbury",
            )
        self.assertNotEqual(meta["route"], "research_overview")

    def test_history_provided_for_followup_context(self):
        model = Mock(side_effect=[self.candidate(), {"allow": True, "supported": True}])
        self.assertIsNotNone(
            r.overview(
                "tell me about Canterbury",
                [self.source()],
                [{"role": "user", "content": "I mean Christchurch in New Zealand"}],
                model,
            )
        )
        self.assertIn("Christchurch", model.call_args_list[0].args[0][1]["content"])

    def test_plain_prose_still_requires_source_review(self):
        text = self.candidate()["answer"]
        model = Mock(
            side_effect=[
                json.JSONDecodeError("Expected JSON", text, 0),
                {"allow": True, "supported": True},
            ]
        )
        result = r.overview("tell me about Canterbury", [self.source()], [], model)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], text)
        self.assertEqual(model.call_count, 2)
