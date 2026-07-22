const { getSql, send, cors, readJson, checkAgentToken } = require('../lib/neon');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') { cors(res); res.statusCode = 204; return res.end(); }
  try {
    const sql = getSql();
    if (req.method === 'GET') {
      const rows = await sql`SELECT * FROM agents ORDER BY last_seen DESC NULLS LAST`;
      return send(res, 200, { agents: rows });
    }
    if (req.method === 'POST') {
      if (!checkAgentToken(req)) return send(res, 401, { error: 'unauthorized' });
      const b = await readJson(req);
      const id = b.id || 'local-8gb';
      await sql`
        INSERT INTO agents (id, name, last_seen, comfy_ok, ipplant_path, detail)
        VALUES (
          ${id}, ${b.name || id}, NOW(), ${!!b.comfy_ok},
          ${b.ipplant_path || null}, ${b.detail || ''}
        )
        ON CONFLICT (id) DO UPDATE SET
          last_seen = NOW(),
          comfy_ok = EXCLUDED.comfy_ok,
          ipplant_path = EXCLUDED.ipplant_path,
          detail = EXCLUDED.detail,
          name = EXCLUDED.name
      `;
      return send(res, 200, { ok: true, id });
    }
    return send(res, 405, { error: 'method not allowed' });
  } catch (e) {
    return send(res, e.status || 500, { error: String(e.message || e) });
  }
};
