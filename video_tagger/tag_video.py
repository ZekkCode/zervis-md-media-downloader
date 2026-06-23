#!/usr/bin/env python3
import argparse
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LABELS = BASE_DIR / "labels.json"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def flatten_labels(labels: dict) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for group, tags in labels.items():
        if group in {"blocked_rules", "safe_general"}:
            continue
        for tag in tags:
            prompt = tag.lstrip("#").replace("_", " ")
            items.append((group, tag, prompt))
    return items


def extract_frames(video: Path, out_dir: Path, every_seconds: int, max_frames: int) -> list[Path]:
    pattern = out_dir / "frame_%04d.jpg"
    run([
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video),
        "-vf",
        f"fps=1/{every_seconds}",
        "-frames:v",
        str(max_frames),
        str(pattern),
    ])
    return sorted(out_dir.glob("frame_*.jpg"))


def keyword_scores(text: str, labels: dict) -> dict[str, float]:
    normalized = re.sub(r"[^a-z0-9#]+", " ", text.lower())
    scores: dict[str, float] = {}
    for tags in labels.values():
        for tag in tags:
            word = tag.lstrip("#").lower()
            if word and word in normalized:
                scores[tag] = max(scores.get(tag, 0.0), 0.92)
    return scores


def clip_scores(frames: list[Path], labels: dict, model_name: str, pretrained: str) -> dict[str, float]:
    import torch
    import open_clip
    from PIL import Image

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, _, preprocess = open_clip.create_model_and_transforms(
        model_name,
        pretrained=pretrained,
        device=device,
    )
    tokenizer = open_clip.get_tokenizer(model_name)

    label_rows = flatten_labels(labels)
    texts = [f"adult video category: {prompt}" for _, _, prompt in label_rows]

    with torch.no_grad():
        text_tokens = tokenizer(texts).to(device)
        text_features = model.encode_text(text_tokens)
        text_features /= text_features.norm(dim=-1, keepdim=True)

        aggregate = torch.zeros(len(label_rows), device=device)
        used = 0
        for frame in frames:
            image = preprocess(Image.open(frame).convert("RGB")).unsqueeze(0).to(device)
            image_features = model.encode_image(image)
            image_features /= image_features.norm(dim=-1, keepdim=True)
            probs = (100.0 * image_features @ text_features.T).softmax(dim=-1)[0]
            aggregate += probs
            used += 1

    if not used:
        return {}

    aggregate = aggregate / used
    return {
        tag: float(score)
        for (_, tag, _), score in zip(label_rows, aggregate.detach().cpu().tolist())
    }


def build_description(title: str, top_tags: list[str], category: str) -> str:
    vibe = ", ".join(top_tags[:6]) if top_tags else "belum kebaca kuat"
    if category == "adult":
        return (
            f"Video '{title}' kebaca sebagai konten adult/NSFW. "
            f"Vibe utamanya: {vibe}. Cocok buat arsip tag otomatis dan filter kategori."
        )
    return (
        f"Video '{title}' belum kebaca sebagai adult kuat. "
        f"Tag yang paling nyangkut: {vibe}."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    parser.add_argument("--every-seconds", type=int, default=5)
    parser.add_argument("--max-frames", type=int, default=12)
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--model", default="ViT-B-32")
    parser.add_argument("--pretrained", default="laion2b_s34b_b79k")
    parser.add_argument("--no-clip", action="store_true")
    args = parser.parse_args()

    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    video = args.video.resolve()
    title = video.stem

    scores = keyword_scores(title, labels)
    frames: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="video_tagger_") as tmp:
        tmp_dir = Path(tmp)
        if shutil.which("ffmpeg"):
            frames = extract_frames(video, tmp_dir, args.every_seconds, args.max_frames)

        if frames and not args.no_clip:
            for tag, score in clip_scores(frames, labels, args.model, args.pretrained).items():
                scores[tag] = max(scores.get(tag, 0.0), score)

    top = sorted(scores.items(), key=lambda item: item[1], reverse=True)[: args.top_k]
    top_tags = [tag for tag, _ in top if tag not in labels.get("blocked_rules", [])]
    adult_label_tags = {
        tag
        for group, tags in labels.items()
        if group not in {"safe_general", "blocked_rules"}
        for tag in tags
    }
    adult_score = sum(score for tag, score in top if tag in adult_label_tags)
    category = "adult" if adult_score > 0.15 else "general"
    confidence = round(float(top[0][1]) if top else 0.0, 4)

    result = {
        "media_title": title,
        "media_description": build_description(title, top_tags, category),
        "classification": {
            "status": "ok",
            "category": category,
            "tags": top_tags,
            "confidence": confidence,
        },
        "debug": {
            "frames_used": len(frames),
            "scores": {tag: round(score, 4) for tag, score in top},
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
