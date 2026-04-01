"""
candidate_ax4_light 모델 설치 완료를 대기하고 벤치마크를 실행하는 스크립트.

Usage:
  python scripts/wait_and_benchmark_ax4.py
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Any

import httpx

PROJECT_ROOT = Path(__file__).parent.parent
OLLAMA_API = "http://localhost:11434"
CHECK_INTERVAL = 60  # 60초마다 확인
MAX_WAIT_TIME = 7200  # 최대 2시간 대기

def get_installed_models() -> List[str]:
    """Ollama에 설치된 모델 목록 반환."""
    try:
        response = httpx.get(f"{OLLAMA_API}/api/tags", timeout=10)
        response.raise_for_status()
        data = response.json()
        return [m["name"] for m in data.get("models", [])]
    except Exception as e:
        print(f"[ERROR] 모델 목록 조회 실패: {e}")
        return []

def wait_for_model(model_name: str = "skt/A.X-4.0-Light") -> bool:
    """candidate_ax4_light 모델 설치 완료 대기."""
    print(f"[*] '{model_name}' 모델 설치 완료 대기 중...")
    elapsed = 0
    
    while elapsed < MAX_WAIT_TIME:
        models = get_installed_models()
        if any(model_name in m for m in models):
            print(f"[OK] '{model_name}' 모델 설치 완료!")
            return True
        
        remaining = MAX_WAIT_TIME - elapsed
        print(f"[*] {elapsed}초 경과... (최대 {remaining}초 남음)")
        time.sleep(CHECK_INTERVAL)
        elapsed += CHECK_INTERVAL
    
    print(f"[ERROR] 최대 대기 시간({MAX_WAIT_TIME}초) 초과")
    return False

def run_benchmark() -> bool:
    """candidate_ax4_light 벤치마크 실행."""
    print("\n[*] candidate_ax4_light 벤치마크 실행 중...")
    cmd = [
        "python",
        "scripts/run_week3_model_benchmark.py",
        "--config", "configs/week3_model_benchmark.yaml",
        "--cases", "docs/40_delivery/week3/model_test_assets/evaluation_set.json",
        "--output-dir", "logs/evaluation/week3",
        "--model", "candidate_ax4_light"
    ]
    
    try:
        result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        
        if result.returncode == 0:
            print("[OK] 벤치마크 실행 완료")
            return True
        else:
            print(f"[ERROR] 벤치마크 실행 실패 (exit code: {result.returncode})")
            return False
    except Exception as e:
        print(f"[ERROR] 벤치마크 실행 중 오류: {e}")
        return False

def main():
    """메인 실행 함수."""
    print("="*60)
    print("candidate_ax4_light 모델 설치 & 벤치마크 파이프라인")
    print("="*60)
    
    # Step 1: 모델 설치 대기
    if not wait_for_model():
        print("\n[ABORT] 모델 설치 대기 실패. 수동으로 설치해주세요:")
        print("  ollama pull skt/A.X-4.0-Light")
        return 1
    
    # Step 2: 벤치마크 실행
    if not run_benchmark():
        return 1
    
    print("\n[OK] 모든 작업 완료!")
    return 0

if __name__ == "__main__":
    exit(main())
