# 한국주식 신호 알림판 (GitHub Pages)

평일 15:47(KST)에 GitHub가 자동으로 `kr_mobile.py`를 실행해서
`https://아이디.github.io/kr-signal-board/` 에 알림판을 올립니다.

## 처음 한 번 설정 (10분)

1. github.com 로그인 → 오른쪽 위 **+** → **New repository**
   - 이름: `kr-signal-board`, **Public** 선택 → Create repository
2. 새 저장소 화면에서 **uploading an existing file** 클릭
   → 이 폴더의 `kr_mobile.py`, `README.md`, `.github` 폴더를 통째로 끌어다 놓기 → **Commit changes**
   - `.github` 폴더가 안 보이면(숨김 폴더): **Add file → Create new file**, 파일 이름에
     `.github/workflows/update.yml` 입력 후 update.yml 내용을 붙여넣고 Commit
3. 저장소 **Settings → Pages** → Source를 **GitHub Actions** 로 선택
4. **Actions** 탭 → 왼쪽 **알림판 갱신** → **Run workflow** 로 한 번 실행 (2~4분)
5. 초록 체크가 뜨면 `https://아이디.github.io/kr-signal-board/` 접속 → 이 주소를 공유

## 알아둘 점

- 주소를 아는 사람은 누구나 볼 수 있고, Public 저장소라 코드도 공개됩니다.
- GitHub 예약 실행은 몇 분~20분 늦게 돌 수 있습니다.
- 60일간 저장소에 변화가 없으면 GitHub가 예약 실행을 멈춥니다. 메일이 오면 Actions 탭에서 다시 켜 주세요.
- 휴대폰 푸시 알림은 기존 Claude 예약 작업이 계속 보냅니다.
