"""Spike S6: the preview rendering stack (P0-T09).

Throwaway evidence-gathering. Findings go to docs/dev/SPIKES.md §S6; the real
viewport is written fresh in P9 (AGENTS.md rule 3).

ADR-008 proposes moderngl inside a QOpenGLWidget. Three things need proving
before P9 relies on it:
  A  can moderngl render a 200k-triangle mesh headlessly at all (standalone EGL)
  B  can Qt's QOpenGLWidget give moderngl a context in a headless container, and
     under which QT_QPA_PLATFORM
  C  what do upload and frame times look like on a software rasteriser

Run:  uv run --with moderngl --with numpy --with pillow --with PySide6 \
          --no-project python spikes/s6_preview.py
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "spikes" / "out" / "s6"
TRIANGLES = 200_000
SIZE = (1280, 720)
FRAMES = 30

VERTEX_SHADER = """
#version 330 core
uniform mat4 mvp;
in vec3 in_position;
in vec3 in_color;
out vec3 v_color;
void main() {
    v_color = in_color;
    gl_Position = mvp * vec4(in_position, 1.0);
}
"""

FRAGMENT_SHADER = """
#version 330 core
in vec3 v_color;
out vec4 f_color;
void main() { f_color = vec4(v_color, 1.0); }
"""

# Run inside the Qt process: QOpenGLWidget must be probed in its own interpreter
# because a failed context leaves Qt in an unusable state.
QT_PROBE = """
import json, sys, time
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication

fmt = QSurfaceFormat()
fmt.setVersion(3, 3)
fmt.setProfile(QSurfaceFormat.CoreProfile)
fmt.setDepthBufferSize(24)
QSurfaceFormat.setDefaultFormat(fmt)

app = QApplication([])
result = {"platform": app.platformName(), "context": False}


class Widget(QOpenGLWidget):
    def initializeGL(self):
        import moderngl

        ctx = moderngl.create_context()
        result["context"] = True
        result["gl_version"] = ctx.info["GL_VERSION"]
        result["gl_renderer"] = ctx.info["GL_RENDERER"]


widget = Widget()
widget.resize(320, 240)
widget.show()
app.processEvents()
image = widget.grabFramebuffer()
app.processEvents()
result["framebuffer_ok"] = not image.isNull() and image.width() == 320
print("S6_JSON " + json.dumps(result))
"""


def make_mesh(triangles: int):
    """A deterministic coloured triangle soup, built with numpy only."""
    import numpy as np

    rng = np.random.default_rng(20260921)
    centres = rng.uniform(-1.0, 1.0, size=(triangles, 1, 3)).astype("f4")
    offsets = rng.uniform(-0.01, 0.01, size=(triangles, 3, 3)).astype("f4")
    positions = centres + offsets
    colors = np.repeat(rng.uniform(0.0, 1.0, size=(triangles, 1, 3)).astype("f4"), 3, axis=1)
    interleaved = np.concatenate([positions, colors], axis=2).reshape(-1, 6)
    return np.ascontiguousarray(interleaved, dtype="f4")


def identity_mvp():
    import numpy as np

    return np.eye(4, dtype="f4").tobytes()


def build_scene(ctx, vertices):
    """Upload the mesh and set up the offscreen target. Returns (vao, fbo, seconds)."""
    import moderngl

    upload_started = time.monotonic()
    vbo = ctx.buffer(vertices.tobytes())
    upload_seconds = time.monotonic() - upload_started

    program = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
    program["mvp"].write(identity_mvp())
    vao = ctx.vertex_array(program, [(vbo, "3f 3f", "in_position", "in_color")])

    colour = ctx.texture(SIZE, 4)
    depth = ctx.depth_renderbuffer(SIZE)
    fbo = ctx.framebuffer(color_attachments=[colour], depth_attachment=depth)
    fbo.use()
    ctx.enable(moderngl.DEPTH_TEST)
    return vao, fbo, upload_seconds


def save_screenshot(fbo) -> tuple[Path | None, int]:
    """Save the render and count pixels that differ from the clear colour.

    "Non-black" would be useless here: the clear colour is not black.
    """
    import numpy as np

    OUT.mkdir(parents=True, exist_ok=True)
    screenshot = OUT / "s6_standalone_200k.png"
    clear_rgb = (13, 13, 20)
    try:
        from PIL import Image
    except ImportError:
        return None, -1

    pixels = fbo.read(components=3)
    image = Image.frombytes("RGB", SIZE, pixels).transpose(Image.FLIP_TOP_BOTTOM)
    image.save(screenshot)
    array = np.asarray(image).astype("int16")
    drawn = int((np.abs(array - np.array(clear_rgb, dtype="int16")).sum(axis=2) > 12).sum())
    return screenshot, drawn


def standalone_render() -> dict[str, object]:
    """Path A: moderngl on its own, the way a CLI thumbnail render would work."""
    import moderngl

    started = time.monotonic()
    ctx = moderngl.create_context(standalone=True, require=330, backend="egl")
    context_seconds = time.monotonic() - started

    vertices = make_mesh(TRIANGLES)
    vao, fbo, upload_seconds = build_scene(ctx, vertices)

    frame_times = []
    for _ in range(FRAMES):
        frame_started = time.monotonic()
        fbo.clear(0.05, 0.05, 0.08, 1.0)
        vao.render()
        ctx.finish()
        frame_times.append(time.monotonic() - frame_started)

    screenshot, drawn = save_screenshot(fbo)
    median_frame = statistics.median(frame_times)
    result = {
        "context_seconds": round(context_seconds, 3),
        "gl_version": ctx.info["GL_VERSION"],
        "gl_renderer": ctx.info["GL_RENDERER"],
        "triangles": TRIANGLES,
        "mesh_megabytes": round(int(vertices.nbytes) / 1_048_576, 1),
        "upload_seconds": round(upload_seconds, 4),
        "median_frame_seconds": round(median_frame, 4),
        "fps_software_rasteriser": round(1.0 / median_frame, 1),
        "screenshot": str(screenshot.relative_to(REPO)) if screenshot else None,
        "screenshot_drawn_pixels": drawn,
        "screenshot_total_pixels": SIZE[0] * SIZE[1],
    }
    ctx.release()
    return result


def qt_probe(platform: str, use_xvfb: bool) -> dict[str, object]:
    """Path B: the real app path. QOpenGLWidget must hand moderngl a context."""
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = platform
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    args = [sys.executable, "-c", QT_PROBE]
    if use_xvfb:
        args = ["xvfb-run", "-a", *args]
    process = subprocess.run(  # noqa: S603 - local interpreter, argv only
        args, capture_output=True, text=True, timeout=300, check=False, env=env
    )
    payload: dict[str, object] = {"exit_code": process.returncode}
    for line in process.stdout.splitlines():
        if line.startswith("S6_JSON "):
            payload.update(json.loads(line[len("S6_JSON ") :]))
    if not payload.get("context"):
        messages = [
            line
            for line in (process.stdout + process.stderr).splitlines()
            if "QOpenGLWidget" in line or "Failed" in line or "not supported" in line
        ]
        payload["diagnostic"] = messages[0] if messages else "no context, no message"
    return payload


def main() -> int:
    try:
        import moderngl  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as exc:
        print(f"missing dependency: {exc}. Re-run with --with moderngl --with numpy")
        return 1

    findings: dict[str, object] = {"standalone_egl": standalone_render()}
    findings["qt_offscreen"] = qt_probe("offscreen", use_xvfb=False)
    findings["qt_xcb_under_xvfb"] = qt_probe("xcb", use_xvfb=True)

    OUT.mkdir(parents=True, exist_ok=True)
    destination = OUT / "s6_findings.json"
    destination.write_text(json.dumps(findings, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(findings, indent=2, sort_keys=True))
    print(f"\nwrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
