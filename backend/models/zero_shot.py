"""Zero-shot captioning and simple VQA with RemoteCLIP (no training).

Captions are built from the best-matching scene labels with their real
softmax probabilities. Zero-shot VQA only covers what CLIP can decide by
comparing prompts: rural/urban and presence. Counting and comparison are
reported as unsupported rather than guessed.
"""
import numpy as np

from models import rsvqa
from models.remoteclip import softmax_scores

SCENE_LABELS = [
    "an airport", "bare land", "a beach", "a bridge", "a commercial area",
    "a dense residential area", "a desert", "farmland", "a forest", "an industrial area",
    "a meadow", "a medium residential area", "mountains", "a park", "a parking lot",
    "a playground", "a pond", "a port", "a railway station", "a river",
    "a sparse residential area", "a stadium", "storage tanks", "a viaduct", "a lake",
    "a wetland", "a highway", "a golf course", "snow", "clouds",
]
SCENE_TEMPLATE = "a satellite image of {}."
RURAL_URBAN_PROMPTS = {"rural": "a satellite image of a rural area.",
                       "urban": "a satellite image of an urban area."}
PRESENCE_PROMPTS = {"yes": "a satellite image containing {}.",
                    "no": "a satellite image with no {}."}


class Unsupported(ValueError):
    """Zero-shot cannot answer this kind of question."""


class ZeroShot:
    """Caches prompt embeddings per encoder so repeated queries stay fast."""

    def __init__(self, encoder):
        self.encoder = encoder
        self._cache = {}

    def _texts(self, texts):
        missing = [t for t in texts if t not in self._cache]
        if missing:
            for text, emb in zip(missing, self.encoder.encode_texts(missing)):
                self._cache[text] = emb
        return np.stack([self._cache[t] for t in texts])

    def scene_scores(self, image_embedding):
        prompts = [SCENE_TEMPLATE.format(label) for label in SCENE_LABELS]
        probs = softmax_scores(self.encoder, image_embedding, self._texts(prompts))
        order = np.argsort(-probs)
        return [(SCENE_LABELS[i], float(probs[i])) for i in order]

    def caption(self, image_embedding, top_k=3, min_prob=0.05):
        scores = self.scene_scores(image_embedding)
        top = scores[0]
        others = [(label, p) for label, p in scores[1:top_k] if p >= min_prob]
        text = f"A satellite image of {top[0]} ({top[1]:.0%})."
        if others:
            text += " Also possible: " + ", ".join(f"{label} ({p:.0%})" for label, p in others) + "."
        return text, top[1], scores[:top_k]

    def answer(self, image_embedding, question):
        """Return (canonical_answer, probability, question_type). Raises Unsupported."""
        qtype = rsvqa.question_type(question)
        if qtype == rsvqa.RURAL_URBAN:
            return self._pick(image_embedding, RURAL_URBAN_PROMPTS) + (qtype,)
        if qtype == rsvqa.PRESENCE:
            obj = rsvqa.presence_object(question)
            if not obj:
                raise Unsupported("could not find what the presence question asks about")
            prompts = {a: p.format(obj) for a, p in PRESENCE_PROMPTS.items()}
            return self._pick(image_embedding, prompts) + (qtype,)
        raise Unsupported(f"zero-shot RemoteCLIP cannot answer '{qtype}' questions")

    def _pick(self, image_embedding, prompts):
        answers = list(prompts)
        probs = softmax_scores(self.encoder, image_embedding, self._texts(list(prompts.values())))
        best = int(np.argmax(probs))
        return answers[best], float(probs[best])
