const { send, cors } = require('../lib/neon');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') { cors(res); res.statusCode = 204; return res.end(); }
  send(res, 200, {
    ok: true,
    product: 'lexiipplant',
    producer: 'lexi_ai/ipplant',
    copyright: 'steven8kay',
    time: new Date().toISOString(),
  });
};
