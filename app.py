
from __future__ import annotations

import json
from pathlib import Path

from nicegui import app, ui

from frameflow.core import (
    BASE_DIR, UPLOAD_DIR, EXPORT_DIR, ProjectManager, media_kind,
)
from frameflow.renderer import render_project, RenderError, ffmpeg_available

manager = ProjectManager()
selected_clip_id: str | None = None
accent = "#70e1ff"

app.add_static_files("/media", str(UPLOAD_DIR))
app.add_static_files("/exports", str(EXPORT_DIR))

ui.colors(primary="#70e1ff", secondary="#a78bfa", accent="#70e1ff")


def notify(message: str, color: str = "positive") -> None:
    ui.notify(message, type=color)


def fmt_time(value: float) -> str:
    seconds = max(0, int(value))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def refresh_workspace() -> None:
    refresh_assets.refresh()
    refresh_timeline.refresh()
    refresh_inspector.refresh()
    project_duration_label.set_text(f"{fmt_time(manager.project.duration)} total")
    clip_count_label.set_text(f"{len(manager.project.clips)} clips")


@ui.refreshable
def refresh_assets() -> None:
    if not any(UPLOAD_DIR.iterdir()):
        ui.label("Your media library is empty. Import videos, images or audio to begin.").classes("empty")
        return
    for path in sorted(UPLOAD_DIR.iterdir(), key=lambda item: item.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        try:
            kind = media_kind(path.name)
        except ValueError:
            continue
        with ui.row().classes("asset-row items-center"):
            icon = {"video": "movie", "image": "image", "audio": "graphic_eq"}[kind]
            ui.icon(icon).classes("text-cyan-300 text-xl")
            with ui.column().classes("gap-0 flex-grow"):
                ui.label(path.name).classes("text-sm font-medium break-all")
                ui.label(kind.upper()).classes("text-[10px] tracking-widest text-slate-500")
            if kind == "audio":
                ui.button("Use audio", on_click=lambda p=path.name: assign_audio(p)).props("dense flat color=secondary")
            else:
                ui.button("Add", on_click=lambda p=path.name: add_clip(p)).props("dense flat color=primary")


@ui.refreshable
def refresh_timeline() -> None:
    rows = manager.project.timeline()
    if not rows:
        ui.label("Your timeline is waiting for its first clip. Add media from the library.").classes("empty")
        return
    for row in rows:
        clip = row["clip"]
        active = clip.id == selected_clip_id
        with ui.row().classes("timeline-clip items-center w-full").style(
            "border-color:#70e1ff;background:#172b3c" if active else ""
        ):
            ui.button(
                f"{clip.kind.upper()}  {Path(clip.filename).name[:28]}",
                on_click=lambda cid=clip.id: select_clip(cid),
            ).props("flat no-caps").classes("flex-grow justify-start")
            ui.label(f"{fmt_time(row['start'])} – {fmt_time(row['end'])}").classes("text-xs text-slate-400")
            ui.button(icon="content_cut", on_click=lambda cid=clip.id: split_selected(cid)).props("flat dense")
            ui.button(icon="delete", on_click=lambda cid=clip.id: delete_clip(cid)).props("flat dense color=negative")
    if manager.project.audio_filename:
        ui.label(f"Audio track: {manager.project.audio_filename}").classes("text-xs text-cyan-200 mt-2")


@ui.refreshable
def refresh_inspector() -> None:
    clip = next((item for item in manager.project.clips if item.id == selected_clip_id), None)
    if clip is None:
        ui.label("Select a timeline clip to edit its source in and out points.").classes("empty")
        return
    ui.label("SELECTED CLIP").classes("eyebrow")
    ui.label(Path(clip.filename).name).classes("font-semibold break-all")
    start_input = ui.number("Source in (seconds)", value=clip.source_in, min=0, step=0.1).classes("w-full")
    end_value = clip.source_out if clip.source_out is not None else clip.source_in + clip.length
    end_input = ui.number("Source out (seconds)", value=end_value, min=0.1, step=0.1).classes("w-full")
    def apply_trim() -> None:
        try:
            manager.trim_clip(clip.id, float(start_input.value or 0), float(end_input.value or 0))
            refresh_workspace()
            notify("Clip trim updated.")
        except ValueError as error:
            notify(str(error), "negative")
    ui.button("Apply trim", on_click=apply_trim).props("color=primary unelevated")
    ui.separator()
    ui.label("TEXT OVERLAYS").classes("eyebrow")
    text_field = ui.textarea("Overlay text", placeholder="Add a title or caption").classes("w-full")
    with ui.row().classes("w-full"):
        overlay_start = ui.number("Start", value=0, min=0, step=0.1).classes("flex-grow")
        overlay_end = ui.number("End", value=max(1, manager.project.duration), min=0.1, step=0.1).classes("flex-grow")
    def add_overlay() -> None:
        text = (text_field.value or "").strip()
        if not text:
            notify("Enter some text first.", "warning")
            return
        from frameflow.core import TextOverlay
        manager.project.overlays.append(TextOverlay(
            id=__import__("uuid").uuid4().hex[:10],
            text=text,
            start=float(overlay_start.value or 0),
            end=float(overlay_end.value or 1),
        ))
        manager.save()
        refresh_workspace()
        notify("Text overlay added.")
    ui.button("Add text overlay", on_click=add_overlay).props("color=secondary outline")
    for overlay in manager.project.overlays:
        with ui.row().classes("items-center w-full"):
            ui.label(f"{overlay.text[:28]}  ({fmt_time(overlay.start)}–{fmt_time(overlay.end)})").classes("text-xs flex-grow")
            ui.button(icon="close", on_click=lambda oid=overlay.id: delete_overlay(oid)).props("flat dense color=negative")


def select_clip(clip_id: str) -> None:
    global selected_clip_id
    selected_clip_id = clip_id
    refresh_timeline.refresh()
    refresh_inspector.refresh()


def add_clip(filename: str) -> None:
    try:
        manager.add_clip(filename)
        global selected_clip_id
        selected_clip_id = manager.project.clips[-1].id
        refresh_workspace()
        notify("Media added to timeline.")
    except Exception as error:
        notify(str(error), "warning")


def assign_audio(filename: str) -> None:
    manager.project.audio_filename = filename
    manager.save()
    refresh_workspace()
    notify("Project soundtrack updated.")


def split_selected(clip_id: str) -> None:
    clip = next((item for item in manager.project.clips if item.id == clip_id), None)
    if not clip:
        return
    try:
        manager.split_clip(clip_id, clip.length / 2)
        refresh_workspace()
        notify("Clip split into two segments.")
    except ValueError as error:
        notify(str(error), "negative")


def delete_clip(clip_id: str) -> None:
    global selected_clip_id
    manager.remove_clip(clip_id)
    if selected_clip_id == clip_id:
        selected_clip_id = None
    refresh_workspace()
    notify("Clip removed.")


def delete_overlay(overlay_id: str) -> None:
    manager.project.overlays = [item for item in manager.project.overlays if item.id != overlay_id]
    manager.save()
    refresh_workspace()


async def handle_upload(event) -> None:
    try:
        name = Path(event.file.name).name
        content = await event.file.read()
        kind = manager.import_file(name, content)
        refresh_workspace()
        notify(f"{name} imported as {kind}.")
    except Exception as error:
        notify(str(error), "negative")


def save_project() -> None:
    manager.project.name = project_name.value or "Untitled project"
    manager.project.aspect_ratio = aspect_select.value or "16:9"
    manager.save()
    notify("Project saved on this server.")


def export_video() -> None:
    save_project()
    status_label.set_text("Rendering video…")
    try:
        output = render_project(manager.project)
        status_label.set_text("Export complete")
        ui.notify(f"Export complete: {output.name}", type="positive")
        ui.download(f"/exports/{output.name}")
    except RenderError as error:
        status_label.set_text("Export failed")
        notify(str(error), "negative")


def clear_project() -> None:
    global selected_clip_id
    manager.clear_project()
    selected_clip_id = None
    refresh_workspace()
    notify("Project timeline cleared.")


@ui.page("/")
def index() -> None:
    global project_name, aspect_select, project_duration_label, clip_count_label, status_label
    ui.add_head_html("""
    <meta name="theme-color" content="#080d18">
    <meta name="description" content="FrameFlow Studio Python video editing workspace">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap" rel="stylesheet">
    """)
    ui.add_css("""
    body { background:#080d18; color:#e8eef8; font-family:'DM Sans',sans-serif; }
    .ff-title { font-family:'Space Grotesk',sans-serif; letter-spacing:-.04em; }
    .panel { background:#101827; border:1px solid #243248; border-radius:16px; }
    .eyebrow { color:#70e1ff; font-size:10px; letter-spacing:.18em; font-weight:700; }
    .muted { color:#8c9bb2; }
    .empty { color:#8c9bb2; font-size:13px; padding:22px 8px; text-align:center; }
    .asset-row { padding:10px; border:1px solid #26364d; border-radius:10px; margin-bottom:8px; background:#0c1422; }
    .timeline-clip { padding:8px 10px; border:1px solid #31415a; background:#111e30; border-radius:10px; margin-bottom:7px; }
    .q-field__control { background:#0b1422 !important; }
    .q-btn { border-radius:9px; }
    """)
    with ui.column().classes("w-full max-w-[1600px] mx-auto p-4 md:p-6 gap-4"):
        with ui.row().classes("items-center justify-between w-full"):
            with ui.row().classes("items-center gap-3"):
                with ui.avatar().classes("bg-cyan-300 text-slate-950 font-black"):
                    ui.label("F")
                with ui.column().classes("gap-0"):
                    ui.label("FRAMEFLOW STUDIO").classes("ff-title text-lg md:text-xl font-bold")
                    ui.label("PYTHON VIDEO WORKSPACE · VERSION 2.0").classes("eyebrow")
            with ui.row().classes("items-center"):
                ui.button("Save project", icon="save", on_click=save_project).props("outline color=primary")
                ui.button("Export MP4", icon="movie", on_click=export_video).props("unelevated color=primary")
        with ui.row().classes("items-center gap-3 w-full"):
            project_name = ui.input("Project name", value=manager.project.name).classes("flex-grow")
            aspect_select = ui.select(
                {"16:9": "16:9 Landscape", "9:16": "9:16 Portrait", "1:1": "1:1 Square", "4:5": "4:5 Social"},
                value=manager.project.aspect_ratio, label="Canvas"
            ).classes("w-48")
        with ui.row().classes("w-full items-start gap-4"):
            with ui.column().classes("panel p-4 w-full md:w-[320px] gap-3"):
                ui.label("MEDIA LIBRARY").classes("eyebrow")
                ui.label("Import video, image and audio files").classes("text-sm muted")
                ui.upload(on_upload=handle_upload, multiple=True, auto_upload=True).props(
                    'accept="video/*,image/*,audio/*" flat bordered'
                ).classes("w-full")
                ui.separator()
                refresh_assets()
            with ui.column().classes("flex-grow min-w-0 gap-4"):
                with ui.column().classes("panel p-4 w-full gap-3"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label("PREVIEW").classes("eyebrow")
                        ui.label("Local media preview").classes("text-xs muted")
                    first_video = next((c for c in manager.project.clips if c.kind == "video"), None)
                    if first_video:
                        ui.video(f"/media/{first_video.filename}").classes("w-full max-h-[420px]")
                    else:
                        with ui.column().classes("w-full min-h-[230px] items-center justify-center rounded-xl").style("background:radial-gradient(circle at 50% 40%,#19324b,#0a111d 65%)"):
                            ui.label("F").classes("ff-title text-6xl font-bold text-cyan-200")
                            ui.label("Your next story starts here").classes("text-lg font-semibold")
                            ui.label("Import footage and build your sequence below.").classes("text-sm muted")
                with ui.column().classes("panel p-4 w-full gap-3"):
                    with ui.row().classes("items-center justify-between w-full"):
                        ui.label("TIMELINE").classes("eyebrow")
                        with ui.row().classes("items-center gap-3"):
                            project_duration_label = ui.label(f"{fmt_time(manager.project.duration)} total").classes("text-xs muted")
                            clip_count_label = ui.label(f"{len(manager.project.clips)} clips").classes("text-xs muted")
                    ui.label("VIDEO / IMAGE TRACK").classes("text-[10px] tracking-widest text-slate-500")
                    refresh_timeline()
                    ui.separator()
                    ui.label("AUDIO").classes("text-[10px] tracking-widest text-slate-500")
                    ui.label(manager.project.audio_filename or "No soundtrack assigned. Choose an audio file from the media library.").classes("text-xs muted")
                    ui.separator()
                    ui.label("EDITING").classes("eyebrow")
                    ui.label("Select a clip to trim it. Use the scissors icon to split it at the midpoint. Add title overlays from the Inspector.").classes("text-xs muted")
                with ui.row().classes("items-center justify-between w-full"):
                    status_label = ui.label("Ready").classes("text-xs muted")
                    ui.button("Clear timeline", icon="delete_sweep", on_click=clear_project).props("flat color=negative")
            with ui.column().classes("panel p-4 w-full md:w-[300px] gap-3"):
                ui.label("INSPECTOR").classes("eyebrow")
                refresh_inspector()
                ui.separator()
                ui.label("EXPORT ENGINE").classes("eyebrow")
                ui.label("FFmpeg available" if ffmpeg_available() else "FFmpeg not detected on this server").classes(
                    "text-sm " + ("text-emerald-300" if ffmpeg_available() else "text-amber-300")
                )
                ui.label("MP4 · H.264 · 30 fps · AAC audio when a soundtrack is assigned").classes("text-xs muted")
        ui.label("Projects and imported media are stored on the server running FrameFlow. Back up the data/ folder regularly.").classes("text-xs muted")


if __name__ in {"__main__", "__mp_main__"}:
    ui.run(
        title="FrameFlow Studio",
        host="0.0.0.0",
        port=int(__import__("os").environ.get("PORT", "8080")),
        reload=False,
        show=False,
        storage_secret=__import__("os").environ.get("FRAMEFLOW_SECRET", "change-this-secret-before-deployment"),
    )
