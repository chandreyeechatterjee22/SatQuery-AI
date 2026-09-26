import pytest

from intent import classify_intent


@pytest.mark.parametrize(
    "query, expected",
    [
        ("Where is the vegetation?", "vegetation"),
        ("Show me green cover", "vegetation"),
        ("Which crop fields are here?", "vegetation"),
        ("Which regions are potentially flooded?", "flood"),
        ("Where are the water bodies?", "water"),
        ("Is there a LAKE nearby?", "water"),
        ("Find the river", "water"),
        ("What is the weather today?", "unknown"),
        ("", "unknown"),
    ],
)
def test_classify_intent(query, expected):
    assert classify_intent(query) == expected


def test_flood_takes_priority_over_water():
    assert classify_intent("flood water extent") == "flood"


def test_vegetation_takes_priority_over_flood():
    # Existing keyword order: vegetation is checked first.
    assert classify_intent("flooded crop fields") == "vegetation"
