"""4-band (B, G, R, NIR) ResNet-18 land-cover patch classifier fine-tuned on BigEarthNet v2.

Shared by the runtime and ml/landcover_patch (one network definition, one input
adapter). The model sees 120 x 120 px patches at 10 m (1.2 km) and predicts the
19 BigEarthNet (CORINE 2018) classes as multi-label probabilities. It says which
classes are present in a patch, not how much area they cover.

Input contract: surface reflectance x 10000 (Sentinel-2 L2A scale). Reflectance
in 0-1 is rescaled; anything else (e.g. Cartosat-2S DNs) runs but is flagged as
out of the training distribution. Every input is resampled to 10 m first.
"""
import importlib.util
import threading

import numpy as np

import settings

MODEL_NAME = "resnet18-4band-bigearthnet"
BANDS = ("blue", "green", "red", "nir")
PATCH = 120            # pixels at 10 m, as in BigEarthNet
TARGET_RES_M = 10.0
ARTIFACT_FORMAT = 1

CLASS_NAMES = [
    "agriculture_with_natural_vegetation", "agro_forestry_areas", "arable_land", "beaches_dunes_sands",
    "broad_leaved_forest", "coastal_wetlands", "complex_cultivation_patterns", "coniferous_forest",
    "industrial_commercial_units", "inland_waters", "inland_wetlands", "marine_waters", "mixed_forest",
    "moors_heathland_sclerophyllous_vegetation", "natural_grassland_sparse_vegetation", "pastures",
    "permanent_crops", "transitional_woodland_shrub", "urban_fabric",
]
BUILT_CLASSES = ("urban_fabric", "industrial_commercial_units")

_M_PER_DEG = 111_320.0


class MissingBands(ValueError):
    """The image lacks one of the blue/green/red/nir roles."""


# --- network -----------------------------------------------------------------------

def build_network(num_classes=len(CLASS_NAMES), imagenet_init=False):
    """ResNet-18 with a 4-channel first conv (B, G, R, NIR).

    With ``imagenet_init`` the RGB filters are copied from ImageNet weights into
    B/G/R order, NIR gets a copy of the red filter, and the conv is scaled by 3/4
    so activations keep their magnitude with four inputs instead of three.
    """
    import torch
    import torchvision

    weights = torchvision.models.ResNet18_Weights.IMAGENET1K_V1 if imagenet_init else None
    net = torchvision.models.resnet18(weights=weights)
    old = net.conv1
    net.conv1 = torch.nn.Conv2d(4, 64, kernel_size=7, stride=2, padding=3, bias=False)
    if imagenet_init:
        with torch.no_grad():
            net.conv1.weight.copy_(adapt_rgb_conv(old.weight))
    net.fc = torch.nn.Linear(net.fc.in_features, num_classes)
    return net


def adapt_rgb_conv(w_rgb):
    """(out, 3, k, k) filters in R, G, B order -> (out, 4, k, k) in B, G, R, NIR order.

    NIR reuses the red filter; everything is scaled by 3/4 so the summed response
    over four inputs matches the original three.
    """
    import torch
    return torch.stack([w_rgb[:, 2], w_rgb[:, 1], w_rgb[:, 0], w_rgb[:, 0]], dim=1) * 0.75


# --- input adapter ------------------------------------------------------------------------

def target_shape(meta):
    """(height, width) of the image resampled to 10 m, and the source resolution in metres."""
    res = meta["resolution"]
    if res["units"] == "metres":
        rx, ry = res["x"], res["y"]
    elif res["units"] == "degrees":
        b = meta["bounds"]
        lat = np.radians((b["top"] + b["bottom"]) / 2)
        rx, ry = res["x"] * _M_PER_DEG * np.cos(lat), res["y"] * _M_PER_DEG
    else:  # no CRS: nothing to resample from, assume 10 m
        return (meta["height"], meta["width"]), None
    h = max(1, round(meta["height"] * ry / TARGET_RES_M))
    w = max(1, round(meta["width"] * rx / TARGET_RES_M))
    return (h, w), round(float((rx + ry) / 2), 3)


def prepare_input(path, meta, bands):
    """Read B, G, R, NIR resampled to 10 m as float32 reflectance x 10000.

    Returns (array (4, H, W), info dict for the trace). Raises MissingBands.
    """
    import rasterio
    from rasterio.enums import Resampling

    roles = bands.get("roles", {})
    missing = [b for b in BANDS if b not in roles]
    if missing:
        raise MissingBands(f"the land-cover model needs {', '.join(BANDS)} bands; missing: {', '.join(missing)}")
    (h, w), src_res = target_shape(meta)
    downsampling = h <= meta["height"]
    with rasterio.open(path) as src:
        data = src.read([roles[b] for b in BANDS], out_shape=(4, h, w), masked=True,
                        resampling=Resampling.average if downsampling else Resampling.bilinear)
    arr = data.astype("float32").filled(np.nan)
    finite = arr[np.isfinite(arr)]
    p99 = float(np.percentile(finite, 99)) if finite.size else 0.0
    if 0 < p99 <= 2.0:
        arr *= 10000.0
        scale = "reflectance 0-1, rescaled x10000"
    elif 100 <= p99 <= 12000:
        scale = "reflectance x10000 (Sentinel-2 L2A scale)"
    else:
        scale = "unknown scale (not reflectance x10000); predictions are out of distribution"
    return arr, {"resampled_to_m": TARGET_RES_M, "source_resolution_m": src_res,
                 "shape_10m": [h, w], "input_scale": scale,
                 "in_distribution": scale.startswith("reflectance")}


def resize_nearest(array, shape):
    """Nearest-neighbour resize of a 2-D map to ``shape`` (same extent)."""
    h, w = array.shape
    rows = np.minimum((np.arange(shape[0]) + 0.5) * h / shape[0], h - 1).astype(int)
    cols = np.minimum((np.arange(shape[1]) + 0.5) * w / shape[1], w - 1).astype(int)
    return array[rows][:, cols]


def windows(height, width, size=PATCH, stride=PATCH // 2):
    """Top-left corners of windows covering the image (the last row/column is flush)."""
    def starts(n):
        if n <= size:
            return [0]
        s = list(range(0, n - size + 1, stride))
        if s[-1] != n - size:
            s.append(n - size)
        return s
    return [(r, c) for r in starts(height) for c in starts(width)]


# --- inference -----------------------------------------------------------------------------

class PatchClassifier:
    def __init__(self, artifact):
        import torch

        if artifact.get("format") != ARTIFACT_FORMAT:
            raise ValueError(f"unsupported land-cover checkpoint format {artifact.get('format')!r}")
        if tuple(artifact["bands"]) != BANDS:
            raise ValueError(f"checkpoint bands {artifact['bands']} != expected {BANDS}")
        self.class_names = list(artifact["class_names"])
        self.net = build_network(len(self.class_names))
        self.net.load_state_dict(artifact["state_dict"])
        self.net.eval()
        self.mean = np.asarray(artifact["mean"], dtype="float32")[:, None, None]
        self.std = np.asarray(artifact["std"], dtype="float32")[:, None, None]
        self.meta = artifact.get("meta", {})
        self._torch = torch

    @classmethod
    def load(cls, path):
        import torch
        return cls(torch.load(path, map_location="cpu", weights_only=True))

    @property
    def trace_info(self):
        return {"model": MODEL_NAME, "version": self.meta.get("version"), "bands": list(BANDS),
                "trained_on": self.meta.get("trained_on")}

    def predict_patches(self, patches, batch_size=64):
        """(N, 4, 120, 120) reflectance x 10000 -> (N, classes) sigmoid probabilities."""
        torch = self._torch
        x = np.nan_to_num((np.asarray(patches, dtype="float32") - self.mean) / self.std)
        out = []
        with torch.inference_mode():
            for i in range(0, len(x), batch_size):
                out.append(torch.sigmoid(self.net(torch.from_numpy(x[i:i + batch_size]))).numpy())
        return np.concatenate(out) if out else np.zeros((0, len(self.class_names)), dtype="float32")

    def scene_score(self, image, classes=BUILT_CLASSES, stride=PATCH // 2):
        """Scene-level score: mean over windows of max P(class in ``classes``). Returns (score, windows)."""
        _, h, w = image.shape
        padded = image
        if h < PATCH or w < PATCH:
            padded = np.pad(image, ((0, 0), (0, max(0, PATCH - h)), (0, max(0, PATCH - w))), mode="reflect")
        corners = windows(*padded.shape[1:], stride=stride)
        probs = self.predict_patches(np.stack([padded[:, r:r + PATCH, c:c + PATCH] for r, c in corners]))
        idx = [self.class_names.index(c) for c in classes]
        return float(probs[:, idx].max(axis=1).mean()), len(corners)

    def score_map(self, image, classes=BUILT_CLASSES, stride=PATCH // 2):
        """Per-pixel score: max over the covering windows of max P(class in ``classes``).

        ``image`` is (4, H, W) at 10 m. Images smaller than a patch are reflect-padded.
        Returns (score map (H, W), number of windows).
        """
        _, h, w = image.shape
        padded = image
        if h < PATCH or w < PATCH:
            padded = np.pad(image, ((0, 0), (0, max(0, PATCH - h)), (0, max(0, PATCH - w))), mode="reflect")
        ph, pw = padded.shape[1:]
        corners = windows(ph, pw, stride=stride)
        probs = self.predict_patches(np.stack([padded[:, r:r + PATCH, c:c + PATCH] for r, c in corners]))
        idx = [self.class_names.index(c) for c in classes]
        scores = probs[:, idx].max(axis=1)
        out = np.zeros((ph, pw), dtype="float32")
        for (r, c), s in zip(corners, scores):
            np.maximum(out[r:r + PATCH, c:c + PATCH], s, out=out[r:r + PATCH, c:c + PATCH])
        return out[:h, :w], len(corners)


_lock = threading.Lock()
_model, _model_key = None, None


def availability():
    for module in ("torch", "torchvision"):
        if importlib.util.find_spec(module) is None:
            return False, f"Python package '{module}' is not installed (pip install -r requirements-ml.txt)."
    path = settings.landcover_patch_path()
    if not path.is_file():
        return False, f"No land-cover model at {path} (train it with ml/landcover_patch/train.py)."
    return True, None


def get_model():
    """Load (and cache) the classifier; None if unavailable. Reloads if the file changed."""
    global _model, _model_key
    ok, _ = availability()
    if not ok:
        return None
    path = settings.landcover_patch_path()
    key = (str(path), path.stat().st_mtime_ns)
    with _lock:
        if _model is None or _model_key != key:
            _model, _model_key = PatchClassifier.load(path), key
    return _model
