"""
Streamlit UI 서버 실행 스크립트

Usage:
    python scripts/run_ui.py
    또는
    streamlit run app/ui/Home.py
"""

import subprocess
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent

if __name__ == "__main__":
    print("🎨 Streamlit UI 시작...")
    
    streamlit_app = project_root / "app" / "ui" / "Home.py"
    
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(streamlit_app)],
        cwd=str(project_root),
    )
