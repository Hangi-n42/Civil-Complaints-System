# SK Telecom A.X-4.0-Light 빠른 설정 가이드

## 📥 Step 1: GGUF 모델 수동 다운로드

다음 링크에서 원하는 버전을 다운로드하세요:

### 추천 버전 (Q4_K_M - 균형잡힌 품질)
- **파일**: A.X-4.0-Light-Q4_K_M.gguf (4.44GB)
- **다운로드**: https://huggingface.co/mykor/A.X-4.0-Light-gguf/resolve/main/A.X-4.0-Light-Q4_K_M.gguf
- **다운로드 도구**: 
  - IDM (Internet Download Manager) 추천
  - 또는 `aria2c` 사용: `aria2c -x 10 "URL"`

### 경량 버전 (Q3_K_S - 더 빠름)
- **파일**: A.X-4.0-Light-Q3_K_S.gguf (3.27GB)
- **다운로드**: https://huggingface.co/mykor/A.X-4.0-Light-gguf/resolve/main/A.X-4.0-Light-Q3_K_S.gguf

---

## 📂 Step 2: Ollama 모델 디렉토리에 배치

다운로드 완료 후:

```powershell
# 디렉토리 생성
$modelDir = "$env:USERPROFILE\.ollama\models\ax4light"
New-Item -ItemType Directory -Path $modelDir -Force

# 다운로드한 파일을 다음 경로로 이동/복사:
# C:\Users\{YourUsername}\.ollama\models\ax4light\model.gguf
```

---

## 🔧 Step 3: Ollama Modelfile 생성

`$env:USERPROFILE\.ollama\models\ax4light\Modelfile` 생성:

```dockerfile
FROM ./model.gguf

PARAMETER temperature 0.2
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_ctx 2048
PARAMETER num_predict 256

SYSTEM """당신은 한국어 민원 처리 전문가입니다. 
사용자의 요청을 정확하게 분석하고 관련 정보를 제공하세요."""
```

---

## ✅ Step 4: Ollama 로컬 모델 생성

```powershell
# PowerShell 관리자 권한으로 실행
cd "$env:USERPROFILE\.ollama\models\ax4light"

# Ollama 모델 생성
ollama create ax4-light-local -f Modelfile
```

---

## 🧪 Step 5: 모델 테스트

```powershell
# 모델이 정상 작동하는지 테스트
ollama run ax4-light-local "민원 신청 방법을 알려줘"

# 또는 Ollama 모델 목록 확인
ollama list | grep ax4
```

---

## 🚀 Step 6: 벤치마크 실행

모델이 정상 작동 확인 후:

```powershell
cd C:\Projects\AI-Civil-Affairs-Systems

python scripts/run_week3_model_benchmark.py `
  --config configs/week3_model_benchmark.yaml `
  --cases docs/40_delivery/week3/model_test_assets/evaluation_set.json `
  --output-dir logs/evaluation/week3 `
  --model candidate_ax4_light
```

---

## 📝 설정 확인

✅ **진행 상황**:
- [x] `configs/week3_model_benchmark.yaml` 업데이트 완료
  - `model_name: skt/A.X-4.0-Light` → `ax4-light-local`

⏳ **다음 할 일**:
1. GGUF 파일 다운로드 & 배치
2. Modelfile 생성 & `ollama create` 실행
3. 벤치마크 실행

---

## 🆘 문제 해결

**Q: Ollama create 실패 (permission denied)**
- A: PowerShell을 관리자 권한으로 실행

**Q: 모델이 로드되지 않음 (out of memory)**
- A: Q2_K (2.81GB) 더 작은 버전으로 시도

**Q: 네트워크 다운로드 느림**
- A: IDM/aria2 등 멀티스레드 다운로더 사용, 또는 VPN 변경
