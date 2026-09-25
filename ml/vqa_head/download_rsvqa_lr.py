"""Download RSVQA-LR (Lobry et al., 2020; CC-BY-4.0) from Zenodo and verify md5 checksums.

Usage (PowerShell, from the repo root):
    .\\.venv\\Scripts\\python.exe ml\\vqa_head\\download_rsvqa_lr.py [--out data\\rsvqa_lr]

Only the split files and images are fetched (~135 MB). Files already present
with the right checksum are skipped. The output folder is git-ignored.
"""
import argparse
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

RECORD = "https://zenodo.org/api/records/6344334/files"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "data" / "rsvqa_lr"

FILES = {
    "Images_LR.zip": "2329258d74d54600628b8652a0e42672",
    "LR_split_train_images.json": "7d1e7c099c65e39b3e773578cdabe79a",
    "LR_split_train_questions.json": "935d59a05d126496fe61c541b4ab2d55",
    "LR_split_train_answers.json": "a5ff787f9977b0050b9bbf4e32bbb533",
    "LR_split_val_images.json": "7a9f267d2cd106025c45a2b68dce5351",
    "LR_split_val_questions.json": "67b99979ebd468330355d656bf4d6d29",
    "LR_split_val_answers.json": "61ba49ece26c989f81a9a1e2fe0d475b",
    "LR_split_test_images.json": "4a5ae90a5686bbcffd1d7ec06ddbb692",
    "LR_split_test_questions.json": "9bddc53d7399a43378f743ec0ff1f95f",
    "LR_split_test_answers.json": "f925d70eb74bb4094966670cb4c2f840",
}


def md5(path, chunk=1 << 20):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def download(name, expected_md5, out_dir):
    target = out_dir / name
    if target.exists() and md5(target) == expected_md5:
        print(f"ok (cached)  {name}")
        return target
    url = f"{RECORD}/{name}/content"
    tmp = target.with_suffix(target.suffix + ".part")
    print(f"downloading  {name}")
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
        while block := resp.read(1 << 20):
            out.write(block)
    actual = md5(tmp)
    if actual != expected_md5:
        tmp.unlink()
        raise SystemExit(f"checksum mismatch for {name}: expected {expected_md5}, got {actual}")
    tmp.replace(target)
    print(f"ok           {name}")
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)

    for name, checksum in FILES.items():
        download(name, checksum, args.out)

    images_dir = args.out / "Images_LR"
    if not images_dir.is_dir() or not any(images_dir.iterdir()):
        print("extracting   Images_LR.zip")
        with zipfile.ZipFile(args.out / "Images_LR.zip") as zf:
            zf.extractall(args.out)
    print(f"RSVQA-LR ready in {args.out}")


if __name__ == "__main__":
    sys.exit(main())
