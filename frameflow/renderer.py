
from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .core import EXPORT_DIR, UPLOAD_DIR, Project


class RenderError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _canvas(aspect: str) -> tuple[int, int]:
    return {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1": (1080, 1080),
        "4:5": (1080, 1350),
    }.get(aspect, (1920, 1080))


def _text_image(text: str, width: int, height: int, font_size: int, path: Path) -> None:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]
    font = None
    for candidate in font_candidates:
        if Path(candidate).exists():
            font = ImageFont.truetype(candidate, font_size)
            break
    if font is None:
        font = ImageFont.load_default()
    safe_text = text[:180]
    bounds = draw.multiline_textbbox((0, 0), safe_text, font=font, align="center", spacing=8, stroke_width=2)
    text_w = bounds[2] - bounds[0]
    text_h = bounds[3] - bounds[1]
    x = (width - text_w) // 2
    y = int(height * 0.78 - text_h / 2)
    draw.multiline_text(
        (x, y), safe_text, font=font, fill=(255, 255, 255, 255),
        align="center", spacing=8, stroke_width=2, stroke_fill=(0, 0, 0, 220),
    )
    image.save(path)


def render_project(project: Project) -> Path:
    if not project.clips:
        raise RenderError("Add at least one video or image clip before exporting.")
    if not ffmpeg_available():
        raise RenderError("FFmpeg is not installed. Install FFmpeg and make sure it is available on PATH.")

    width, height = _canvas(project.aspect_ratio)
    output = EXPORT_DIR / f"frameflow_{uuid.uuid4().hex[:8]}.mp4"
    temporary_files: list[Path] = []
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]

    for clip in project.clips:
        source = UPLOAD_DIR / clip.filename
        if not source.exists():
            raise RenderError(f"Missing media file: {clip.filename}")
        if clip.kind == "image":
            command += ["-loop", "1", "-t", str(clip.length), "-i", str(source)]
        else:
            command += ["-ss", str(clip.source_in), "-t", str(clip.length), "-i", str(source)]

    audio_index = None
    if project.audio_filename:
        audio_path = UPLOAD_DIR / project.audio_filename
        if audio_path.exists():
            audio_index = len(project.clips)
            command += ["-i", str(audio_path)]

    filters = []
    labels = []
    for index, clip in enumerate(project.clips):
        label = f"v{index}"
        filters.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps=30,format=yuv420p[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[vbase]")
    current_label = "vbase"

    overlay_inputs = []
    for index, overlay in enumerate(project.overlays):
        png_path = EXPORT_DIR / f"overlay_{uuid.uuid4().hex[:8]}.png"
        _text_image(overlay.text, width, height, overlay.font_size, png_path)
        temporary_files.append(png_path)
        overlay_inputs.append((len(project.clips) + (1 if audio_index is not None else 0) + index, overlay, png_path))
        command += ["-loop", "1", "-i", str(png_path)]

    for overlay_number, (input_index, overlay, _png) in enumerate(overlay_inputs):
        next_label = f"vtext{overlay_number}"
        filters.append(
            f"[{current_label}][{input_index}:v]overlay=0:0:"
            f"enable='between(t,{overlay.start},{overlay.end})':shortest=1[{next_label}]"
        )
        current_label = next_label

    filters.append(f"[{current_label}]format=yuv420p[vout]")
    command += ["-filter_complex", ";".join(filters), "-map", "[vout]"]

    if audio_index is not None:
        command += ["-map", f"{audio_index}:a:0?", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        command += ["-an"]

    command += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-movflags", "+faststart", str(output),
    ]

    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        if result.returncode != 0:
            raise RenderError(result.stderr[-2500:] or "FFmpeg could not render this project.")
    except subprocess.TimeoutExpired as exc:
        raise RenderError("Export exceeded the 30-minute processing limit.") from exc
    finally:
        for path in temporary_files:
            path.unlink(missing_ok=True)

    return output
