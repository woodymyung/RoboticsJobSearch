"""로컬 서버 + 버튼 갱신.

실행:
  cd JD
  python3 serve.py            # http://localhost:8000 자동 안내

기능:
  - jobs.csv / index.html 정적 서빙
  - POST /scrape  : 스크래퍼(scraper/build_csv.py) 실행 후 jobs.csv 갱신
    → index.html의 '🔄 갱신' 버튼이 이 엔드포인트를 호출한다.
"""
import json
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 8000


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def do_POST(self):
        if self.path.rstrip("/") != "/scrape":
            self.send_error(404)
            return
        print("[serve] 스크래핑 시작...")
        try:
            proc = subprocess.run(
                [sys.executable, "build_csv.py"],
                cwd=str(ROOT / "scraper"),
                capture_output=True, text=True, timeout=900,
            )
            ok = proc.returncode == 0
            tail = (proc.stdout or "")[-400:] + (proc.stderr or "")[-200:]
        except Exception as e:
            ok, tail = False, str(e)
        body = json.dumps({"ok": ok, "log": tail}, ensure_ascii=False).encode("utf-8")
        self.send_response(200 if ok else 500)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        print(f"[serve] 스크래핑 완료 (ok={ok})")

    def end_headers(self):
        # CSV가 캐시되어 갱신이 안 보이는 문제 방지
        if self.path.endswith(".csv"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    print(f"▶ http://localhost:{PORT} 에서 열기 (종료: Ctrl+C)")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
