import sys
from pathlib import Path

# scripts/forecasting/*.py are flat scripts, not a package — make them importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
