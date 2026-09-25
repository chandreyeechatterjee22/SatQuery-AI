# VQA head for RSVQA-LR

A small MLP on top of **frozen** RemoteCLIP ViT-B/32 embeddings:
`[image, question, image * question]` (3 x 512) -> 512 -> 512 -> answer vocabulary.
It is trained on the RSVQA-LR **train** split. The best epoch is chosen on **val**.
The **test** split is only read by `eval.py`.

The network definition, question-type detection and image preprocessing are
imported from `backend/models`, so training uses exactly the code the API serves with.
At inference, answers that never occurred for the detected question type in TRAIN
are masked out (for example, a count question cannot get "yes").

| File | Purpose |
|---|---|
| `download_rsvqa_lr.py` | Downloads RSVQA-LR from Zenodo (CC-BY-4.0, ~135 MB), checks md5, unzips images |
| `config.yaml` | Paths, answer vocabulary, network and training settings |
| `train.py` | Embeds train/val (cached), trains, saves the head + `train_log.json` |
| `eval.py` | Accuracy per question type, OA and AA on TEST, compared with the zero-shot and majority baselines |

Everything is written under `data/`, which git ignores.

## Run (PowerShell, from the repo root)

```powershell
.\.venv\Scripts\python.exe backend\scripts\download_remoteclip.py
.\.venv\Scripts\python.exe ml\vqa_head\download_rsvqa_lr.py
.\.venv\Scripts\python.exe ml\vqa_head\train.py
.\.venv\Scripts\python.exe ml\vqa_head\eval.py
```

The head is saved to `data/models/vqa_head/rsvqa_lr_head.pt`, which is the backend's
default `VQA_HEAD_PATH`. Once that file exists, `rs_vqa` uses it automatically.

Tests (synthetic data, no downloads): `cd ml; ..\.venv\Scripts\python.exe -m pytest`

## Notes

- Count answers in RSVQA-LR are raw integers (0 to over 16,000). The head predicts
  exact numbers from the TRAIN vocabulary, and `eval.py` scores exact match. It also
  reports binned count accuracy (0, 1-10, 11-100, 101-1000, >1000), the convention of
  the original RSVQA paper, as a separate column. Do not mix the two when comparing
  with published numbers.
- RSVQA-LR has no "area" questions (those are in RSVQA-HR), so this head has not
  learned to answer them.
