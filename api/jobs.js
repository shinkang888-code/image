const { getSql, send, cors, readJson, checkAgentToken } = require('../lib/neon');
const crypto = require('crypto');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') { cors(res); res.statusCode = 204; return res.end(); }
  try {
    const sql = getSql();
    if (req.method === 'GET') {
      const url = new URL(req.url, 'http://localhost');
      const status = url.searchParams.get('status');
      const rows = status
        ? await sql`SELECT * FROM jobs WHERE status = ${status} ORDER BY created_at ASC LIMIT 100`
        : await sql`SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100`;
      return send(res, 200, { jobs: rows });
    }
    if (req.method === 'POST') {
      if (!checkAgentToken(req)) return send(res, 401, { error: 'unauthorized' });
      const body = await readJson(req);
      const action = body.action || 'create';

      if (action === 'create') {
        const id = body.id || `J-${crypto.randomBytes(6).toString('hex')}`;
        const type = body.type || 'generate';
        const payload = body.payload || {};
        await sql`
          INSERT INTO jobs (id, type, payload, status)
          VALUES (${id}, ${type}, ${JSON.stringify(payload)}, 'pending')
        `;
        await sql`
          INSERT INTO events (kind, message, job_id)
          VALUES ('info', ${'job created: ' + type}, ${id})
        `;
        return send(res, 201, { id, status: 'pending' });
      }

      if (action === 'claim') {
        // Agent claims oldest pending job
        const agentId = body.agent_id || 'local';
        const rows = await sql`
          UPDATE jobs SET status = 'running', agent_id = ${agentId}, started_at = NOW()
          WHERE id = (
            SELECT id FROM jobs WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1
          )
          RETURNING *
        `;
        return send(res, 200, { job: rows[0] || null });
      }

      if (action === 'finish') {
        const { id, status, error } = body;
        await sql`
          UPDATE jobs SET status = ${status || 'done'}, error = ${error || null}, finished_at = NOW()
          WHERE id = ${id}
        `;
        await sql`
          INSERT INTO events (kind, message, job_id)
          VALUES (${status === 'failed' ? 'error' : 'success'}, ${'job ' + (status || 'done')}, ${id})
        `;
        return send(res, 200, { ok: true });
      }

      return send(res, 400, { error: 'unknown action' });
    }
    return send(res, 405, { error: 'method not allowed' });
  } catch (e) {
    return send(res, e.status || 500, { error: String(e.message || e) });
  }
};
