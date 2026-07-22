const { getSql, send, cors, readJson, checkAgentToken } = require('../lib/neon');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') { cors(res); res.statusCode = 204; return res.end(); }
  try {
    const sql = getSql();
    if (req.method === 'GET') {
      const url = new URL(req.url, 'http://localhost');
      const category = url.searchParams.get('category');
      const limit = Math.min(parseInt(url.searchParams.get('limit') || '60', 10), 200);
      const rows = category
        ? await sql`
            SELECT * FROM assets WHERE category = ${category}
            ORDER BY created_at DESC LIMIT ${limit}
          `
        : await sql`SELECT * FROM assets ORDER BY created_at DESC LIMIT ${limit}`;
      const stats = await sql`SELECT * FROM category_stats ORDER BY category, subcategory`;
      return send(res, 200, { assets: rows, stats });
    }
    if (req.method === 'POST') {
      if (!checkAgentToken(req)) return send(res, 401, { error: 'unauthorized' });
      const a = await readJson(req);
      await sql`
        INSERT INTO assets (
          id, prompt_id, category, subcategory, tag, seed, width, height,
          bytes_webp, local_path, drive_file_id, share_url, sha256,
          prompt_full, negative, iplant_line, copyright_holder, schema_json
        ) VALUES (
          ${a.id}, ${a.prompt_id}, ${a.category}, ${a.subcategory}, ${a.tag || null},
          ${a.seed || 0}, ${a.width || null}, ${a.height || null},
          ${a.bytes_webp || null}, ${a.local_path || null}, ${a.drive_file_id || null},
          ${a.share_url || null}, ${a.sha256 || null},
          ${a.prompt_full || null}, ${a.negative || null}, ${a.iplant_line || null},
          ${a.copyright_holder || 'steven8kay'}, ${JSON.stringify(a.schema_json || {})}
        )
        ON CONFLICT (id) DO UPDATE SET
          share_url = EXCLUDED.share_url,
          drive_file_id = EXCLUDED.drive_file_id,
          schema_json = EXCLUDED.schema_json
      `;
      return send(res, 201, { ok: true, id: a.id });
    }
    return send(res, 405, { error: 'method not allowed' });
  } catch (e) {
    return send(res, e.status || 500, { error: String(e.message || e) });
  }
};
