"""Trained VQA head: frozen RemoteCLIP image + question embeddings -> MLP -> answer.

The network is defined here and imported by ml/vqa_head/train.py, so the
runtime and training always share one definition. The saved artifact holds
the weights, the answer vocabulary and, per question type, which answers were
seen in training (used to mask impossible answers, e.g. "yes" to a count).
"""
import importlib.util
import threading

import numpy as np

import settings
from models import rsvqa

ARTIFACT_FORMAT = 1


def build_network(dim, hidden, n_answers, dropout):
    import torch.nn as nn

    class VqaHeadNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.mlp = nn.Sequential(
                nn.Linear(3 * dim, hidden), nn.GELU(), nn.Dropout(dropout),
                nn.Linear(hidden, hidden), nn.GELU(), nn.Dropout(dropout),
                nn.Linear(hidden, n_answers),
            )

        def forward(self, image, question):
            import torch
            return self.mlp(torch.cat([image, question, image * question], dim=-1))

    return VqaHeadNet()


def type_mask(answers, answers_by_type, qtype):
    """Boolean mask over the vocabulary of answers allowed for a question type."""
    allowed = answers_by_type.get(qtype)
    if not allowed:
        return np.ones(len(answers), dtype=bool)
    allowed = set(allowed)
    return np.array([a in allowed for a in answers], dtype=bool)


class VqaHead:
    def __init__(self, artifact):
        import torch

        if artifact.get("format") != ARTIFACT_FORMAT:
            raise ValueError(f"unsupported VQA head format {artifact.get('format')!r}")
        cfg = artifact["network"]
        self.net = build_network(cfg["dim"], cfg["hidden"], len(artifact["answers"]), cfg["dropout"])
        self.net.load_state_dict(artifact["state_dict"])
        self.net.eval()
        self.answers = list(artifact["answers"])
        self.answers_by_type = artifact.get("answers_by_type", {})
        self.meta = artifact.get("meta", {})
        self._torch = torch

    @classmethod
    def load(cls, path):
        import torch
        return cls(torch.load(path, map_location="cpu", weights_only=True))

    def predict(self, image_embedding, question_embedding, question, top_k=3):
        """Return (answer, probability, question_type, top_k list of (answer, prob))."""
        qtype = rsvqa.question_type(question)
        probs = self.probabilities(image_embedding[None], question_embedding[None], [qtype])[0]
        order = np.argsort(-probs)[:top_k]
        best = int(order[0])
        return (self.answers[best], float(probs[best]), qtype,
                [(self.answers[i], float(probs[i])) for i in order if probs[i] > 0])

    def probabilities(self, image_embeddings, question_embeddings, qtypes):
        """Batch softmax over answers, with impossible answers for each type masked out."""
        torch = self._torch
        with torch.inference_mode():
            logits = self.net(torch.from_numpy(np.asarray(image_embeddings, dtype="float32")),
                              torch.from_numpy(np.asarray(question_embeddings, dtype="float32")))
            logits = logits.numpy().astype("float64")
        masks = np.stack([type_mask(self.answers, self.answers_by_type, t) for t in qtypes])
        logits = np.where(masks, logits, -np.inf)
        logits -= logits.max(axis=1, keepdims=True)
        exp = np.exp(logits)
        return exp / exp.sum(axis=1, keepdims=True)


_lock = threading.Lock()
_head = None
_head_key = None


def availability():
    if importlib.util.find_spec("torch") is None:
        return False, "Python package 'torch' is not installed."
    path = settings.vqa_head_path()
    if not path.is_file():
        return False, f"No trained VQA head at {path} (train it with ml/vqa_head/train.py)."
    return True, None


def get_head():
    """Load (and cache) the head; reloads if the file changed. None if unavailable."""
    global _head, _head_key
    ok, _ = availability()
    if not ok:
        return None
    path = settings.vqa_head_path()
    key = (str(path), path.stat().st_mtime_ns)
    with _lock:
        if _head is None or _head_key != key:
            _head, _head_key = VqaHead.load(path), key
    return _head
