"""Compatibility import for the historical filename ``Render.py``."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

_spec = spec_from_file_location("_render_impl", Path(__file__).with_name("Render.py"))
if _spec is None or _spec.loader is None:
    raise ImportError("cannot load Render.py")
_module = module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)
for _name in dir(_module):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_module, _name)
