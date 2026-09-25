import numpy as np
import pytest

from models.remoteclip import softmax_scores
from models.zero_shot import (PRESENCE_PROMPTS, RURAL_URBAN_PROMPTS, SCENE_LABELS, SCENE_TEMPLATE,
                              Unsupported, ZeroShot)
from tests.fakes import FakeEncoder, unit


def encoder_matching(text):
    """An encoder whose image embedding equals the embedding of ``text``."""
    return FakeEncoder(image_vector=unit(text))


def test_softmax_scores_sum_to_one():
    enc = FakeEncoder()
    probs = softmax_scores(enc, enc.image_vector, enc.encode_texts(["a", "b", "c"]))
    assert probs.shape == (3,) and np.isclose(probs.sum(), 1.0)


def test_caption_picks_matching_scene_with_probability():
    enc = encoder_matching(SCENE_TEMPLATE.format("farmland"))
    text, prob, top = ZeroShot(enc).caption(enc.image_vector, top_k=3)
    assert text.startswith("A satellite image of farmland (")
    assert top[0][0] == "farmland" and prob == top[0][1] and prob > 0.5
    assert len(top) == 3 and top[0][1] >= top[1][1] >= top[2][1]


def test_caption_only_lists_plausible_alternatives():
    enc = encoder_matching(SCENE_TEMPLATE.format("a forest"))
    text, prob, _ = ZeroShot(enc).caption(enc.image_vector, min_prob=1.1)
    assert "Also possible" not in text


def test_prompt_embeddings_are_cached():
    enc = encoder_matching(SCENE_TEMPLATE.format("farmland"))
    zs = ZeroShot(enc)
    zs.caption(enc.image_vector)
    zs.caption(enc.image_vector)
    assert enc.text_calls == 1
    assert len(zs._cache) == len(SCENE_LABELS)


def test_rural_urban():
    enc = encoder_matching(RURAL_URBAN_PROMPTS["urban"])
    answer, prob, qtype = ZeroShot(enc).answer(enc.image_vector, "Is it a rural or an urban area")
    assert (answer, qtype) == ("urban", "rural_urban") and prob > 0.5


@pytest.mark.parametrize("truth", ["yes", "no"])
def test_presence_uses_object_prompts(truth):
    enc = encoder_matching(PRESENCE_PROMPTS[truth].format("water area"))
    answer, prob, qtype = ZeroShot(enc).answer(enc.image_vector, "Is there a water area?")
    assert (answer, qtype) == (truth, "presence") and 0.5 < prob <= 1.0


@pytest.mark.parametrize("question", ["How many buildings are there?",
                                      "Are there more roads than forests?",
                                      "Why is the river brown?"])
def test_counting_comparison_and_open_questions_are_unsupported(question):
    enc = FakeEncoder()
    with pytest.raises(Unsupported):
        ZeroShot(enc).answer(enc.image_vector, question)
