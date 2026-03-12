from src.policy import Offer, evaluate_offer


def test_policy_allows_reasonable_offer():
    offer = Offer(title="Concert", section="Lower Bowl", quantity=2, total_usd=100.0)
    decision = evaluate_offer(offer)
    assert decision.allowed is True
