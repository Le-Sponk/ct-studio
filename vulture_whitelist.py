"""Vulture whitelist: names that are used, but only in ways vulture cannot see.

`scripts/check.py` passes this file to `vulture src/ vulture_whitelist.py --min-confidence 80`.
Add an entry only with a comment naming the real user (a Qt slot connected by name, an entry
point, a Blender operator attribute). Regenerate candidates with
`uv run vulture src/ --make-whitelist`, then keep only the justified lines.
"""
