"""Single-image VQA: trained RSVQA head when installed, zero-shot RemoteCLIP otherwise.

Answers are short canonical strings (yes/no, numbers, rural/urban) so they can
be scored against RSVQA directly. Confidence is the softmax probability of the
chosen answer. The trace records which component answered.
"""
from agent import tasks
from agent.registry import Tool, ToolNotAvailable, ToolResult
from agent.tools.clip_common import (encoder_or_unavailable, image_embedding, preview_evidence,
                                     zero_shot_for)
from models import remoteclip, rsvqa, vqa_head
from models.zero_shot import Unsupported

TRAINED_HEAD = "trained_head"
ZERO_SHOT = "zero_shot"


class VqaTool(Tool):
    name = "rs_vqa"
    version = "1.0.0"
    task = tasks.VQA
    description = ("Answer questions about a single image: trained RSVQA-LR head on RemoteCLIP "
                   "embeddings if installed, else zero-shot RemoteCLIP (presence, rural/urban).")
    params = {"question": {"type": "str", "max_length": 500, "required": True}}

    def availability(self):
        return remoteclip.availability()

    def extract_params(self, question, ctx):
        return {"question": question}

    def run(self, ctx, params, query_id):
        question = params["question"]
        encoder = encoder_or_unavailable()
        img = image_embedding(ctx, encoder)

        head, head_error = None, None
        try:
            head = vqa_head.get_head()
        except Exception as exc:  # a broken head file must not hide zero-shot
            head_error = f"{type(exc).__name__}: {exc}"

        if head is not None:
            q = encoder.encode_texts([question])[0]
            answer, probability, qtype, top = head.predict(img, q, question)
            trace = {"answered_by": TRAINED_HEAD, "model": encoder.model_id,
                     "head": {k: head.meta.get(k) for k in ("trained_on", "created", "val_accuracy")}}
        else:
            try:
                answer, probability, qtype = zero_shot_for(encoder).answer(img, question)
            except Unsupported as exc:
                raise ToolNotAvailable(
                    f"{exc}, and no trained VQA head is installed",
                    trace={"answered_by": None, "question_type": rsvqa.question_type(question),
                           "head_available": False, "head_error": head_error}) from exc
            top = [(answer, probability)]
            trace = {"answered_by": ZERO_SHOT, "model": encoder.model_id, "head_error": head_error}

        trace["question_type"] = qtype
        warnings = []
        if qtype == rsvqa.COUNT and not ctx.file(1)["metadata"]["georeferenced"]:
            warnings.append("Counts were learned on 2.56 km Sentinel-2 tiles (10 m pixels). This image has no map "
                            "scale, so treat the number as a rough guess.")
        return ToolResult(
            answer=answer,
            confidence=probability,
            evidence_images=[preview_evidence(ctx)],
            data={"question_type": qtype, "answered_by": trace["answered_by"], "warnings": warnings,
                  "top_answers": [{"answer": a, "probability": round(p, 4)} for a, p in top]},
            trace={k: v for k, v in trace.items() if v is not None},
        )
