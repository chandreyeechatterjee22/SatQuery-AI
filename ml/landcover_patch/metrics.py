"""Multi-label metrics in numpy: average precision, micro/macro mAP, macro F1."""
import numpy as np


def average_precision(y_true, scores):
    """AP = mean precision at the rank of each positive (ties broken by order). None if no positives."""
    y_true = np.asarray(y_true, dtype=bool)
    n_pos = int(y_true.sum())
    if n_pos == 0:
        return None
    order = np.argsort(-np.asarray(scores), kind="stable")
    hits = y_true[order]
    precision_at_hit = np.cumsum(hits)[hits] / (np.flatnonzero(hits) + 1)
    return float(precision_at_hit.sum() / n_pos)


def evaluate(y_true, probs, class_names, threshold=0.5):
    """Micro mAP, macro mAP (classes with positives), macro F1 at ``threshold``, per-class AP."""
    y_true = np.asarray(y_true, dtype=bool)
    probs = np.asarray(probs)
    per_class = {}
    f1s = []
    pred = probs >= threshold
    for k, name in enumerate(class_names):
        ap = average_precision(y_true[:, k], probs[:, k])
        per_class[name] = None if ap is None else round(ap, 4)
        if y_true[:, k].any():
            tp = int((pred[:, k] & y_true[:, k]).sum())
            fp = int((pred[:, k] & ~y_true[:, k]).sum())
            fn = int((~pred[:, k] & y_true[:, k]).sum())
            f1s.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0)
    aps = [v for v in per_class.values() if v is not None]
    return {
        "micro_map": round(average_precision(y_true.ravel(), probs.ravel()), 4),
        "macro_map": round(float(np.mean(aps)), 4),
        "macro_f1": round(float(np.mean(f1s)), 4),
        "per_class_ap": per_class,
        "n": int(len(y_true)),
    }
