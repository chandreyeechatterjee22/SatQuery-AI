"""Zero-shot captioning with RemoteCLIP: best-matching scene labels with probabilities."""
from agent import tasks
from agent.registry import Tool, ToolResult
from agent.tools.clip_common import (encoder_or_unavailable, image_embedding, preview_evidence,
                                     zero_shot_for)
from models import remoteclip


class CaptionTool(Tool):
    name = "rs_caption"
    version = "1.0.0"
    task = tasks.CAPTION
    description = "Describe a single image by matching it against remote-sensing scene labels (RemoteCLIP, zero-shot)."
    params = {"top_k": {"type": "int", "min": 1, "max": 5, "default": 3}}

    def availability(self):
        return remoteclip.availability()

    def run(self, ctx, params, query_id):
        encoder = encoder_or_unavailable()
        embedding = image_embedding(ctx, encoder)
        text, probability, top = zero_shot_for(encoder).caption(embedding, top_k=params["top_k"])
        return ToolResult(
            answer=text,
            confidence=probability,
            evidence_images=[preview_evidence(ctx)],
            data={"scene_scores": [{"label": label, "probability": round(p, 4)} for label, p in top]},
            trace={"model": encoder.model_id, "method": "zero_shot_scene_labels"},
        )
