"""로컬 서버 + 버튼 갱신 + 닉네임 개인화 저장.

실행:
  cd JD
  python3 serve.py            # http://localhost:8000 자동 안내

기능:
  - jobs.csv / index.html 정적 서빙
  - POST /scrape          : 스크래퍼(scraper/build_csv.py) 실행 후 CSV 갱신
  - GET  /userdata?user=  : 닉네임의 스크랩(찜)/숨김 내역 반환 (기기 간 공유)
  - POST /userdata?user=  : 닉네임의 찜/숨김 내역 저장 (userdata/<nick>.json)
"""
import json
import re
import subprocess
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
USERDATA = ROOT / "userdata"
PORT = 8000


def _safe_user(name):
    """경로 조작 방지: 한글·영숫자·_- 만 허용, 32자 제한."""
    name = (name or "").strip()
    name = re.sub(r"[^0-9A-Za-z가-힣_\-]", "", name)
    return name[:32]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == "/userdata":
            user = _safe_user(parse_qs(parsed.query).get("user", [""])[0])
            if not user:
                return self._json(400, {"error": "no user"})
            f = USERDATA / f"{user}.json"
            data = {"fav": [], "hidden": []}
            if f.exists():
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    pass
            return self._json(200, data)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/userdata":
            user = _safe_user(parse_qs(parsed.query).get("user", [""])[0])
            if not user:
                return self._json(400, {"error": "no user"})
            try:
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n) or b"{}")
                data = {"fav": list(payload.get("fav", [])),
                        "hidden": list(payload.get("hidden", []))}
                USERDATA.mkdir(exist_ok=True)
                (USERDATA / f"{user}.json").write_text(
                    json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return self._json(200, {"ok": True})
            except Exception as e:
                return self._json(500, {"error": str(e)})

        if path == "/scrape":
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
            print(f"[serve] 스크래핑 완료 (ok={ok})")
            return self._json(200 if ok else 500, {"ok": ok, "log": tail})

        self.send_error(404)

    def end_headers(self):
        if self.path.endswith(".csv"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    print(f"▶ http://localhost:{PORT} 에서 열기 (종료: Ctrl+C)")
    ThreadingHTTPServer(("", PORT), Handler).serve_forever()
