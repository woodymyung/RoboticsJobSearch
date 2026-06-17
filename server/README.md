# 개인화 백엔드 (Cloudflare Workers + KV)

닉네임별 찜/숨김 내역을 저장해 **기기 간 동기화**를 제공하는 무료 서버리스 백엔드.
GitHub Pages(정적)에는 서버가 없으므로, 기기 간 공유가 필요하면 이걸 배포해 사용한다.
로컬에서 `serve.py`로 띄우면 동일한 `/userdata` API가 내장돼 있어 이 배포 없이도 동작한다(단, 그 기기/서버 한정).

## API (serve.py와 동일)
- `GET  /userdata?user=<닉네임>` → `{ "fav": [...], "hidden": [...] }`
- `POST /userdata?user=<닉네임>` (body: `{fav, hidden}`) → `{ "ok": true }`

## 배포 (5분, 무료)
```bash
npm i -g wrangler           # Cloudflare CLI
wrangler login              # 브라우저로 Cloudflare 로그인(무료 가입)

cd server
cp wrangler.toml.example wrangler.toml   # wrangler.toml은 gitignore됨(계정·KV id 보호)
wrangler kv namespace create RJS    # 출력된 id를 wrangler.toml의 id= 에 붙여넣기
wrangler deploy                     # → https://robotics-job-userdata.<당신>.workers.dev
```

## 프론트 연결
배포된 Worker 주소를 `index.html`이 바라보게 한다. 둘 중 하나:
- `index.html` 상단의 설정 스크립트에서 `window.RJS_API_BASE = 'https://....workers.dev'` 주석 해제 후 주소 입력
- 또는 브라우저 콘솔에서 `localStorage.setItem('rjs_api','https://....workers.dev')`

설정하면 GitHub Pages에서도 닉네임 로그인 시 어느 기기에서든 같은 찜/숨김 목록을 본다.
주소를 비워두면 같은 출처(`serve.py`)를 호출한다.

> 무료 한도: Workers 1일 10만 요청, KV 충분. 닉네임은 비밀번호가 아니므로 민감정보 저장 금지(찜/숨김 목록 용도).
