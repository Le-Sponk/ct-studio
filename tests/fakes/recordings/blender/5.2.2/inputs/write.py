import os
from pathlib import Path

Path("result.txt").write_text(
    os.environ.get("CT_STUDIO_BLENDER_TEST_PAYLOAD", "generated") + "\n",
    encoding="utf-8",
)
print("saved")
