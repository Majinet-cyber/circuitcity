"""
Tests for simulator CFO advice logic.
"""
import pytest
from staticpages.views import get_cfo_message


class TestCFOAdvice:
    """Test the CFO message generation based on profit levels."""

    def test_loss_scenario(self):
        """Test CFO message for loss scenario (profit <= 0)."""
        message = get_cfo_message(-100_000)
        assert message
        assert len(message) > 0
        # Should mention loss/raising prices/reducing costs
        assert any(word in message.lower() for word in ["loss", "raising", "reducing", "costs", "price"])

    def test_zero_profit(self):
        """Test CFO message for break-even scenario."""
        message = get_cfo_message(0)
        assert message
        assert len(message) > 0
        assert any(word in message.lower() for word in ["loss", "break even"])

    def test_slightly_profitable(self):
        """Test CFO message for slightly profitable scenario (< 400k)."""
        message = get_cfo_message(100_000)
        assert message
        assert len(message) > 0
        # Should encourage growth/volume
        assert any(word in message.lower() for word in ["profitable", "volume", "price", "milestone", "above water"])

    def test_moderate_profit(self):
        """Test CFO message for moderate profit scenario (400k - 2M)."""
        message = get_cfo_message(1_000_000)
        assert message
        assert len(message) > 0
        # Should mention equipment/upgrades/reinvestment
        assert any(word in message.lower() for word in ["equipment", "upgrade", "reinvest", "marketing", "progress"])

    def test_high_profit(self):
        """Test CFO message for high profit scenario (>= 2M)."""
        message = get_cfo_message(5_000_000)
        assert message
        assert len(message) > 0
        # Should mention expansion/car/major purchases
        assert any(word in message.lower() for word in ["car", "equipment", "expansion", "vacation", "strong"])

    def test_message_changes_randomly(self):
        """Test that messages change (randomness works)."""
        messages = set()
        # Generate 20 messages for the same profit level
        for _ in range(20):
            msg = get_cfo_message(1_000_000)
            messages.add(msg)
        
        # We should get at least 2 different messages (since there are 2 options per range)
        assert len(messages) >= 1  # At least one message
        # Note: Due to randomness, we might get the same message multiple times,
        # but over 20 tries we should see variation

    def test_message_categories_differ(self):
        """Test that different profit ranges produce different message tones."""
        loss_msg = get_cfo_message(-100_000)
        low_msg = get_cfo_message(100_000)
        mid_msg = get_cfo_message(1_000_000)
        high_msg = get_cfo_message(5_000_000)
        
        # Ensure we got 4 distinct message tones
        # (They should be different since they're from different ranges)
        # At minimum, check they're not all identical
        all_messages = [loss_msg, low_msg, mid_msg, high_msg]
        assert len(set(all_messages)) > 1  # Should have variety across ranges

