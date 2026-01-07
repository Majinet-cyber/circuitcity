"""
Tests for the quotes feature in dashboard/helpers_quotes.py
"""
from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model

from dashboard.helpers_quotes import get_todays_quotes, get_quote_for_slot, QUOTES


User = get_user_model()


class QuotesTestCase(TestCase):
    """Test the daily quotes feature"""

    def setUp(self):
        """Create a test user"""
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="testpass123")

    def test_quotes_list_has_100_plus_entries(self):
        """Ensure we have at least 100 quotes in the QUOTES list"""
        self.assertGreaterEqual(len(QUOTES), 100, "Should have at least 100 quotes")

    def test_get_todays_quotes_returns_10_quotes(self):
        """Test that get_todays_quotes returns 10 quotes by default"""
        result = get_todays_quotes(self.user)

        self.assertIn("quotes", result)
        self.assertEqual(len(result["quotes"]), 10)
        self.assertEqual(result["count"], 10)

    def test_get_todays_quotes_returns_expected_structure(self):
        """Test that the result has the expected structure"""
        result = get_todays_quotes(self.user)

        # Check that we have slots
        for i in range(1, 11):
            slot_key = f"slot_{i}"
            self.assertIn(slot_key, result)
            self.assertIn("text", result[slot_key])
            self.assertIn("author", result[slot_key])

        # Check that quotes list has correct structure
        for quote in result["quotes"]:
            self.assertIn("text", quote)
            self.assertIn("author", quote)
            self.assertIsInstance(quote["text"], str)
            self.assertIsInstance(quote["author"], str)

        # Check date
        self.assertIn("date", result)
        self.assertIsInstance(result["date"], date)

    def test_get_todays_quotes_is_deterministic(self):
        """Test that the same user on the same day gets the same quotes"""
        result1 = get_todays_quotes(self.user)
        result2 = get_todays_quotes(self.user)

        # Same quotes in same order
        self.assertEqual(result1["quotes"], result2["quotes"])

    def test_get_todays_quotes_works_with_different_users(self):
        """Test that different users get different quotes"""
        user2 = User.objects.create_user(username="testuser2", email="test2@example.com", password="testpass123")

        result1 = get_todays_quotes(self.user)
        result2 = get_todays_quotes(user2)

        # Different users should likely get different first quotes
        # (not guaranteed but very likely with 120+ quotes)
        # We'll just check that both got valid results
        self.assertEqual(len(result1["quotes"]), 10)
        self.assertEqual(len(result2["quotes"]), 10)

    def test_get_quote_for_slot(self):
        """Test getting a single quote for a specific slot"""
        quote = get_quote_for_slot(self.user, slot=1)

        self.assertIn("text", quote)
        self.assertIn("author", quote)
        self.assertIsInstance(quote["text"], str)
        self.assertIsInstance(quote["author"], str)

    def test_get_todays_quotes_with_custom_count(self):
        """Test that we can request a custom number of quotes"""
        result = get_todays_quotes(self.user, count=5)

        self.assertEqual(len(result["quotes"]), 5)
        self.assertEqual(result["count"], 5)

    def test_get_todays_quotes_with_none_user(self):
        """Test that the function gracefully handles None user"""
        result = get_todays_quotes(None)

        self.assertIn("quotes", result)
        self.assertEqual(len(result["quotes"]), 10)
        # Should still work, just using user_id = 0

    def test_quotes_are_from_curated_list(self):
        """Test that returned quotes are actually from our QUOTES list"""
        result = get_todays_quotes(self.user)

        # Build a set of all quote texts from QUOTES
        all_quote_texts = {text for text, author in QUOTES}

        for quote in result["quotes"]:
            self.assertIn(quote["text"], all_quote_texts, f"Quote '{quote['text']}' not found in QUOTES list")
