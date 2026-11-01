
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
EXPORT_DIR = DATA_DIR / "exports"
PROJECT_FILE = DATA_DIR / "project.json"

for directory in (DATA_DIR, UPLOAD_DIR, EXPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    ".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi",
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp"
}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}


def media_kind(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    raise ValueError("This file type is not supported.")


@dataclass
class Clip:
    id: str
    filename: str
    kind: str
    source_in: float = 0.0
    source_out: float | None = None
    duration: float = 5.0

    @property
    def length(self) -> float:
        return max(0.1, float(self.duration))


@dataclass
class TextOverlay:
    id: str
    text: str
    start: float
    end: float
    font_size: int = 48


@dataclass
class Project:
    name: str = "Untitled project"
    aspect_ratio: str = "16:9"
    clips: list[Clip] = field(default_factory=list)
    audio_filename: str | None = None
    overlays: list[TextOverlay] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return sum(clip.length for clip in self.clips)

    def timeline(self) -> list[dict[str, Any]]:
        cursor = 0.0
        rows = []
        for clip in self.clips:
            rows.append({
                "clip": clip,
                "start": cursor,
                "end": cursor + clip.length,
            })
            cursor += clip.length
        return rows


class ProjectManager:
    def __init__(self) -> None:
        self.project = self.load()

    def load(self) -> Project:
        if not PROJECT_FILE.exists():
            return Project()
        try:
            raw = json.loads(PROJECT_FILE.read_text(encoding="utf-8"))
            return Project(
                name=raw.get("name", "Untitled project"),
                aspect_ratio=raw.get("aspect_ratio", "16:9"),
                clips=[Clip(**item) for item in raw.get("clips", [])],
                audio_filename=raw.get("audio_filename"),
                overlays=[TextOverlay(**item) for item in raw.get("overlays", [])],
            )
        except (OSError, ValueError, TypeError, KeyError):
            return Project()

    def save(self) -> None:
        payload = {
            "name": self.project.name,
            "aspect_ratio": self.project.aspect_ratio,
            "clips": [asdict(item) for item in self.project.clips],
            "audio_filename": self.project.audio_filename,
            "overlays": [asdict(item) for item in self.project.overlays],
        }
        temporary = PROJECT_FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temporary.replace(PROJECT_FILE)

    def import_file(self, original_name: str, content: bytes) -> str:
        kind = media_kind(original_name)
        safe_name = Path(original_name).name
        destination = UPLOAD_DIR / f"{uuid.uuid4().hex[:10]}_{safe_name}"
        destination.write_bytes(content)
        if kind == "audio":
            self.project.audio_filename = destination.name
        else:
            default_duration = 5.0
            self.project.clips.append(Clip(
                id=uuid.uuid4().hex[:10],
                filename=destination.name,
                kind=kind,
                duration=default_duration,
            ))
        self.save()
        return kind

    def add_clip(self, filename: str) -> Clip:
        path = UPLOAD_DIR / filename
        if not path.exists():
            raise FileNotFoundError("The selected media file is missing.")
        kind = media_kind(filename)
        if kind == "audio":
            self.project.audio_filename = filename
            self.save()
            raise ValueError("Audio has been assigned as the project soundtrack.")
        clip = Clip(uuid.uuid4().hex[:10], filename, kind, duration=5.0)
        self.project.clips.append(clip)
        self.save()
        return clip

    def split_clip(self, clip_id: str, at_seconds: float) -> None:
        for index, clip in enumerate(self.project.clips):
            if clip.id != clip_id:
                continue
            if at_seconds <= 0.1 or at_seconds >= clip.length - 0.1:
                raise ValueError("The split point must be inside the clip.")
            first = Clip(
                id=uuid.uuid4().hex[:10], filename=clip.filename, kind=clip.kind,
                source_in=clip.source_in,
                source_out=clip.source_in + at_seconds,
                duration=at_seconds,
            )
            second = Clip(
                id=uuid.uuid4().hex[:10], filename=clip.filename, kind=clip.kind,
                source_in=clip.source_in + at_seconds,
                source_out=clip.source_out,
                duration=clip.length - at_seconds,
            )
            self.project.clips[index:index + 1] = [first, second]
            self.save()
            return
        raise ValueError("Select a clip before splitting.")

    def remove_clip(self, clip_id: str) -> None:
        self.project.clips = [clip for clip in self.project.clips if clip.id != clip_id]
        self.save()

    def trim_clip(self, clip_id: str, start: float, end: float) -> None:
        for clip in self.project.clips:
            if clip.id == clip_id:
                if start < 0 or end <= start:
                    raise ValueError("The trim end must be greater than the start.")
                delta = end - start
                clip.source_in = start
                clip.source_out = end
                clip.duration = delta
                self.save()
                return
        raise ValueError("Clip not found.")

    def clear_project(self) -> None:
        self.project = Project()
        self.save()
