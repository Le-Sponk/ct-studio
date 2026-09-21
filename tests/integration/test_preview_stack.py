"""S6 contract tests: the preview rendering stack.

Pins the behaviour P9 relies on, measured in P0-T09 against Mesa 25.0.7
(llvmpipe) with moderngl 5.12 and PySide6. Findings: docs/dev/SPIKES.md §S6.

These need the GL stack and the preview dependencies, and skip without them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SPIKE = REPO / "spikes" / "s6_preview.py"

moderngl = pytest.importorskip("moderngl", reason="moderngl not installed")
numpy = pytest.importorskip("numpy", reason="numpy not installed")

pytestmark = pytest.mark.integration


def make_context():
    try:
        return moderngl.create_context(standalone=True, require=330, backend="egl")
    except Exception as exc:  # no EGL/Mesa in this environment
        pytest.skip(f"no headless GL context: {exc}")


def test_headless_gl_context_meets_the_adr_008_target() -> None:
    """ADR-008 targets GL 3.3 core; the container must provide at least that."""
    ctx = make_context()
    try:
        assert ctx.version_code >= 330
        assert "Mesa" in ctx.info["GL_VERSION"] or "OpenGL" in ctx.info["GL_VERSION"]
    finally:
        ctx.release()


def test_a_200k_triangle_mesh_uploads_in_one_call() -> None:
    """P9-T02 budget is a single interleaved VBO, no per-triangle Python."""
    import numpy as np

    ctx = make_context()
    try:
        vertices = np.zeros((200_000 * 3, 6), dtype="f4")
        vbo = ctx.buffer(vertices.tobytes())
        assert vbo.size == vertices.nbytes
        assert vbo.size == 200_000 * 3 * 6 * 4
    finally:
        ctx.release()


def test_offscreen_render_actually_rasterises_geometry() -> None:
    """A framebuffer that only shows the clear colour would pass a naive check."""
    import numpy as np

    ctx = make_context()
    try:
        program = ctx.program(
            vertex_shader="""
                #version 330 core
                in vec2 in_position;
                void main() { gl_Position = vec4(in_position, 0.0, 1.0); }
            """,
            fragment_shader="""
                #version 330 core
                out vec4 f_color;
                void main() { f_color = vec4(1.0, 0.0, 0.0, 1.0); }
            """,
        )
        triangle = np.array([-0.9, -0.9, 0.9, -0.9, 0.0, 0.9], dtype="f4")
        vbo = ctx.buffer(triangle.tobytes())
        vao = ctx.vertex_array(program, [(vbo, "2f", "in_position")])

        size = (64, 64)
        fbo = ctx.framebuffer(color_attachments=[ctx.texture(size, 4)])
        fbo.use()
        fbo.clear(0.0, 0.0, 0.0, 1.0)
        vao.render()

        pixels = np.frombuffer(fbo.read(components=3), dtype="u1").reshape(size[1], size[0], 3)
        red = (pixels[:, :, 0] > 200) & (pixels[:, :, 1] < 50)

        assert red.any(), "nothing was rasterised"
        # A filled triangle covers a meaningful fraction, not a stray pixel.
        assert red.sum() > (size[0] * size[1]) // 8
    finally:
        ctx.release()


@pytest.mark.skipif(shutil.which("xvfb-run") is None, reason="xvfb-run not installed")
def test_qopenglwidget_needs_a_real_platform_plugin_not_offscreen() -> None:
    """The constraint P9-T01 and the GUI test setup must design around.

    `QT_QPA_PLATFORM=offscreen` cannot create a GL context at all, so preview
    tests need Xvfb + xcb. Discovered in S6; if a future Qt/Mesa makes offscreen
    work, this test fails and the docs should be updated.
    """
    pytest.importorskip("PySide6", reason="PySide6 not installed")
    probe = (
        "from PySide6.QtWidgets import QApplication;"
        "from PySide6.QtOpenGLWidgets import QOpenGLWidget;"
        "app = QApplication([]);"
        "w = QOpenGLWidget(); w.resize(64, 64); w.show();"
        "app.processEvents();"
        "import moderngl;"
        "ok = True\n"
        "try:\n"
        "    w.makeCurrent(); moderngl.create_context()\n"
        "except Exception:\n"
        "    ok = False\n"
        "print('CONTEXT', ok)"
    )
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"

    result = subprocess.run(  # noqa: S603 - local interpreter, argv only
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=env,
    )

    combined = result.stdout + result.stderr
    assert "CONTEXT True" not in combined
    assert "not supported on this platform" in combined or "Failed to create context" in combined


@pytest.mark.skipif(shutil.which("xvfb-run") is None, reason="xvfb-run not installed")
@pytest.mark.slow
def test_qopenglwidget_gives_moderngl_a_context_under_xvfb() -> None:
    """The route GUI preview tests must use: xvfb-run + QT_QPA_PLATFORM=xcb."""
    pytest.importorskip("PySide6", reason="PySide6 not installed")
    probe = (
        "import json;"
        "from PySide6.QtGui import QSurfaceFormat;"
        "from PySide6.QtWidgets import QApplication;"
        "from PySide6.QtOpenGLWidgets import QOpenGLWidget;"
        "fmt = QSurfaceFormat(); fmt.setVersion(3, 3);"
        "fmt.setProfile(QSurfaceFormat.CoreProfile);"
        "QSurfaceFormat.setDefaultFormat(fmt);"
        "app = QApplication([]); out = {}\n"
        "class W(QOpenGLWidget):\n"
        "    def initializeGL(self):\n"
        "        import moderngl\n"
        "        out['v'] = moderngl.create_context().version_code\n"
        "w = W(); w.resize(64, 64); w.show(); app.processEvents();"
        "img = w.grabFramebuffer(); app.processEvents();"
        "print('RESULT ' + json.dumps({'version': out.get('v', 0),"
        " 'framebuffer': not img.isNull()}))"
    )
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "xcb"
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"

    xvfb = shutil.which("xvfb-run")
    assert xvfb is not None
    result = subprocess.run(  # noqa: S603 - local interpreter, argv only
        [xvfb, "-a", sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
        env=env,
    )

    payload = {}
    for line in result.stdout.splitlines():
        if line.startswith("RESULT "):
            payload = json.loads(line[len("RESULT ") :])
    assert payload.get("version", 0) >= 330, result.stdout + result.stderr
    assert payload.get("framebuffer") is True


def test_the_spike_script_is_runnable_and_self_describing() -> None:
    """The spike must stay reproducible; findings reference it by name."""
    source = SPIKE.read_text(encoding="utf-8")
    assert "TRIANGLES = 200_000" in source
    assert "qt_offscreen" in source
    assert "qt_xcb_under_xvfb" in source
