"""Test the plugin without the companion.

  python scripts/send_preset.py ogre        send a built-in preset
  python scripts/send_preset.py off         normal voice
  python scripts/send_preset.py mute|unmute
  python scripts/send_preset.py ping        check the plugin is listening
  python scripts/send_preset.py list
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "companion"))
from osc_client import PluginLink  # noqa: E402

presets = json.loads((Path(__file__).resolve().parent.parent / "companion" / "presets.json").read_text(encoding="utf-8"))
link = PluginLink()
cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

if cmd == "list":
    print("presets:", ", ".join(presets))
elif cmd == "off":
    link.bypass(True)
elif cmd == "mute":
    link.mute(True)
elif cmd == "unmute":
    link.mute(False)
elif cmd == "ping":
    print("plugin answered" if link.ping() else "no answer on port 9001")
elif cmd in presets:
    link.preset(presets[cmd]["params"])
    print(f"sent {cmd}: {presets[cmd]['params']}")
else:
    sys.exit(f"unknown preset '{cmd}'. Try: list")
