/**
 * 로보틱스 채용 사이트 — 닉네임 개인화 백엔드 (Cloudflare Worker + KV)
 *
 * serve.py와 동일한 API:
 *   GET  /userdata?user=<닉네임>  → {fav:[], hidden:[]}
 *   POST /userdata?user=<닉네임>  (body: {fav, hidden}) → 저장
 *
 * GitHub Pages(정적)에서 기기 간 동기화를 위해 사용. 배포: server/README.md 참고.
 * CORS 허용(다른 출처의 Pages에서 호출 가능).
 */
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });
}

function safeUser(s) {
  return (s || "").replace(/[^0-9A-Za-z가-힣_\-]/g, "").slice(0, 32);
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });

    const url = new URL(request.url);
    if (url.pathname.replace(/\/$/, "") !== "/userdata") {
      return new Response("not found", { status: 404, headers: CORS });
    }

    const user = safeUser(url.searchParams.get("user"));
    if (!user) return json({ error: "no user" }, 400);

    if (request.method === "GET") {
      const v = await env.RJS.get("u:" + user);
      return json(v ? JSON.parse(v) : { fav: [], hidden: [] });
    }

    if (request.method === "POST") {
      let p = {};
      try { p = await request.json(); } catch (e) {}
      const data = {
        fav: Array.isArray(p.fav) ? p.fav.slice(0, 5000) : [],
        hidden: Array.isArray(p.hidden) ? p.hidden.slice(0, 5000) : [],
      };
      await env.RJS.put("u:" + user, JSON.stringify(data));
      return json({ ok: true });
    }

    return json({ error: "method not allowed" }, 405);
  },
};
