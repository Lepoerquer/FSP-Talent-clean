import importlib.util
import sys
from pathlib import Path

mock_file = Path(__file__).resolve().parent.parent / "fsp-mock" / "main.py"
spec = importlib.util.spec_from_file_location("fsp_mock_impl", str(mock_file))
module = importlib.util.module_from_spec(spec)
sys.modules["fsp_mock_impl"] = module
spec.loader.exec_module(module)

app = module.app
