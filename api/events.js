const { getSql, send, cors } = require('../lib/neon');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') { cors(res); res.statusCode = 204; return res.end(); }
  try {
    const sql = getSql();
    const url = new URL(req.url, 'http://localhost');
    const limit = Math.min(parseInt(url.searchParams.get('limit') || '50', 10), 200);
    const rows = await sql`
      SELECT id, kind, message, job_id, created_at
      FROM events ORDER BY id DESC LIMIT ${limit}
    `;
    return send(res, 200, { events: rows });
  } catch (e) {
    return send(res, e.status || 500, { error: String(e.message || e) });
  }
};
