import pytest

from models.rsvqa import count_bin, presence_object, question_type


@pytest.mark.parametrize("question, qtype", [
    ("Is it a rural or an urban area", "rural_urban"),
    ("Is this an urban or rural area?", "rural_urban"),
    ("Are there more roads than water areas?", "comp"),
    ("Are there less commercial buildings than roads?", "comp"),
    ("Is the number of water areas equal to the number of forests?", "comp"),
    ("What is the number of commercial buildings?", "count"),
    ("What is the amount of grass areas?", "count"),
    ("How many buildings are there?", "count"),
    ("Is there a grass area?", "presence"),
    ("Is a rectangular farmland present?", "presence"),
    ("Are there any roads?", "presence"),
    ("Does the image contain a river?", "presence"),
    ("Why is the river brown?", "other"),
    ("", "other"),
])
def test_question_type(question, qtype):
    assert question_type(question) == qtype


@pytest.mark.parametrize("question, obj", [
    ("Is there a grass area?", "grass area"),
    ("Is there a small residential building?", "small residential building"),
    ("Are there any roads in the image?", "roads"),
    ("Is a rectangular commercial building present?", "rectangular commercial building"),
    ("Is a heath present?", "heath"),
    ("Does the image contain a river?", "river"),
    ("How many roads?", None),
])
def test_presence_object(question, obj):
    assert presence_object(question) == obj


@pytest.mark.parametrize("answer, expected", [
    ("0", "0"), ("1", "1-10"), ("10", "1-10"), ("11", "11-100"), ("100", "11-100"),
    ("101", "101-1000"), ("1000", "101-1000"), ("16218", ">1000"), ("yes", None), (None, None),
])
def test_count_bin(answer, expected):
    assert count_bin(answer) == expected
