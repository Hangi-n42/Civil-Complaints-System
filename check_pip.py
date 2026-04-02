#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

repo = Path(".").resolve()
pip_exe = repo / ".venv" / "Scripts" / "pip.exe"

print("=== pip.exe 런처 복구 상태 확인 ===")
print(f"pip.exe 존재: {pip_exe.exists()}")

if pip_exe.exists():
    try:
        result = subprocess.run([str(pip_exe), "--version"], capture_output=True, text=True, timeout=5)
        print(f"pip.exe 실행 결과: {result.returncode}")
        if result.returncode == 0:
            print(f"✓ pip.exe 정상 작동")
            print(f"  {result.stdout.strip()}")
        else:
            print(f"✗ pip.exe 오류: {result.stderr[:100]}")
    except Exception as e:
        print(f"✗ pip.exe 실행 실패: {e}")
else:
    print("✗ pip.exe 파일 없음")

# python -m pip 비교
print("\n=== python -m pip 상태 ===")
result = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True, text=True, timeout=5)
print(f"✓ {result.stdout.strip()}")

# plotly 검증
print("\n=== plotly 설치 확인 ===")
result = subprocess.run([sys.executable, "-m", "pip", "show", "plotly"], capture_output=True, text=True, timeout=5)
if result.returncode == 0:
    for line in result.stdout.split("\n")[:2]:
        if line:
            print(f"✓ {line}")
else:
    print("✗ plotly not installed")
