import pytest

from audience_ops.client import Client, Unknown


@pytest.mark.parametrize("body", [None, [], "unexpected", {"brand": "atlas", "contract": 1, "rows": [None]}])
def test_malformed_membership_is_unknown_not_absence_or_unbounded_crash(body):
    client = Client("http://localhost:1", "test-only")
    client.request = lambda *_: (200, body)
    with pytest.raises(Unknown):
        client.membership("atlas")


@pytest.mark.parametrize("body", [None, [], "unexpected"])
def test_malformed_successful_receipt_does_not_authorize_replay(body):
    client = Client("http://localhost:1", "test-only")
    client.request = lambda *_: (200, body)
    with pytest.raises(Unknown):
        client.readback({"brand": "atlas", "person": "100", "effect_id": "f" * 64})
