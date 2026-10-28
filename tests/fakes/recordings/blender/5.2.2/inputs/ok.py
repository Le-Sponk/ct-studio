import sys

print("ARGS", repr(sys.argv[sys.argv.index("--") + 1 :]) if "--" in sys.argv else "[]")
print("ok")
