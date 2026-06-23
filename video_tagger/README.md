# Local Video Tagger

Tagger lokal tanpa API key.

## Run

```bash
cd /mnt/d/telegram-x-video-downloader
/home/zakariamp/openclaw-zakariamp/video-tagger-venv/bin/python video_tagger/tag_video.py downloads/DriveTeleZekk/Topic-21/Topic-21-2.mp4
```

Mode ringan tanpa CLIP, cuma filename/keyword:

```bash
/home/zakariamp/openclaw-zakariamp/video-tagger-venv/bin/python video_tagger/tag_video.py downloads/DriveTeleZekk/Topic-21/Topic-21-2.mp4 --no-clip
```

## Output

```json
{
  "media_title": "Topic-21-2",
  "media_description": "Video 'Topic-21-2' kebaca sebagai konten adult/NSFW...",
  "classification": {
    "status": "ok",
    "category": "adult",
    "tags": ["#jav", "#sex", "#boobs"],
    "confidence": 0.87
  }
}
```

## Notes

- `labels.json` berisi 100+ tag awal.
- `tag_video.py` ambil frame via `ffmpeg`, lalu cocokkan label pakai CLIP lokal.
- Pertama kali pakai CLIP bisa download model weight.
