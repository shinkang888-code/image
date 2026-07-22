const { send, cors, readJson } = require('../lib/neon');

// Mirror Python lip.taxonomy.ai_recommend_weights / alloc for dashboard mode A/B
const DEFAULT = { websource: 30, commerce: 40, aimodel: 30 };
const SUB = {
  websource: { hero: 25, banner: 20, logo: 10, ui_screen: 25, bg: 15, icon_scene: 5 },
  commerce: { pack_hero: 25, label: 20, pdp: 25, detail: 15, lifestyle: 15 },
  aimodel: { female_lookbook: 30, male_lookbook: 25, product_wear: 25, beauty: 10, diversity: 10 },
};

function largestRemainder(total, weights) {
  const keys = Object.keys(weights);
  const s = keys.reduce((a, k) => a + weights[k], 0) || 1;
  const raw = Object.fromEntries(keys.map((k) => [k, (total * weights[k]) / s]));
  const floors = Object.fromEntries(keys.map((k) => [k, Math.floor(raw[k])]));
  let rem = total - Object.values(floors).reduce((a, b) => a + b, 0);
  const order = keys.sort((a, b) => (raw[b] - floors[b]) - (raw[a] - floors[a]));
  for (const k of order) {
    if (rem <= 0) break;
    floors[k] += 1;
    rem -= 1;
  }
  return floors;
}

function recommend(goal) {
  const g = String(goal || 'commerce').toLowerCase();
  if (['site', 'web', 'websource'].includes(g)) return { websource: 50, commerce: 30, aimodel: 20 };
  if (['model', 'lookbook', 'aimodel'].includes(g)) return { websource: 20, commerce: 30, aimodel: 50 };
  if (['balanced', 'equal'].includes(g)) return { websource: 34, commerce: 33, aimodel: 33 };
  return { ...DEFAULT };
}

function alloc(total, weights) {
  const top = largestRemainder(total, weights);
  const quotas = [];
  for (const [cat, n] of Object.entries(top)) {
    const parts = largestRemainder(n, SUB[cat] || { default: 100 });
    for (const [sub, c] of Object.entries(parts)) {
      if (c > 0) quotas.push({ category: cat, subcategory: sub, count: c, key: `${cat}.${sub}` });
    }
  }
  return quotas;
}

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') { cors(res); res.statusCode = 204; return res.end(); }
  if (req.method !== 'POST' && req.method !== 'GET') return send(res, 405, { error: 'method not allowed' });
  const body = req.method === 'POST' ? await readJson(req) : {};
  const url = new URL(req.url, 'http://localhost');
  const total = parseInt(body.total || url.searchParams.get('total') || '1000', 10);
  const goal = body.goal || url.searchParams.get('goal') || 'commerce';
  const weights = body.weights || recommend(goal);
  const quotas = alloc(total, weights);
  send(res, 200, {
    total,
    goal,
    weights,
    quotas,
    defaults: DEFAULT,
    sub_weights: SUB,
    copyright: 'steven8kay',
    producer: 'lexi_ai/ipplant',
  });
};
