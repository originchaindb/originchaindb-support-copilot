const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {test} = require('node:test');
const {JSDOM} = require('jsdom');

async function until(check) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (check()) return;
    await new Promise(resolve => setTimeout(resolve, 10));
  }
  throw new Error('Expected frontend state did not appear');
}

function fixture({failSettings = false} = {}) {
  const dom = new JSDOM(readFileSync('support_copilot/static/index.html', 'utf8'), {
    url: 'http://127.0.0.1:8000/', runScripts: 'outside-only'
  });
  const w = dom.window;
  const source = {id: 'source', source: 'real-fixture.md', version: '1234567890abcdef',
    start_line: 1, end_line: 2, body: '# Fixture product\nExport data from Settings.'};
  const calls = [], events = [];
  let feedback = false;
  w.fetch = async (path, options = {}) => {
    const payload = options.body ? JSON.parse(options.body) : undefined;
    calls.push({path, payload, headers: options.headers});
    let body;
    if (path === '/api/documents') body = [source];
    else if (path === '/api/recent') body = events;
    else if (path === '/api/queue') body = feedback ? [{question: 'export', feedback: 'not_helpful'}] : [];
    else if (path === '/api/settings') body = {indexed_documents: 1, stored_passages: 1,
      snapshot: '1234567890abcdef', namespace: 'fixture', embedding_model: 'embed-fixture',
      answer_model: 'chat-fixture', inference: 'CPU requested', source_bytes: 44,
      vector_payload_bytes: 3072};
    else if (path.startsWith('/api/feedback/')) { feedback = true; body = {saved: true}; }
    else if (path === '/api/ask') {
      body = {id: payload.generate ? 'a'.repeat(32) : null, question: payload.question,
        answer: payload.generate ? '<img src=x onerror=alert(1)> Draft text' : 'No AI answer was generated.',
        status: payload.generate ? 'draft' : 'sources_only', sources: [source],
        citations: payload.generate ? [{...source, quote: 'Export data from Settings.'}] : [],
        created_ms: 1792512000000};
      if (payload.generate) events.push(body);
    } else throw new Error(`Unexpected route: ${path}`);
    const failed = failSettings && path === '/api/settings';
    return {ok: !failed, json: async () => failed ? {error: 'Database unavailable'} : structuredClone(body)};
  };
  w.eval(readFileSync('support_copilot/static/app.js', 'utf8'));
  return {dom, w, calls};
}

test('FAQ loads actual API data and defaults to keyword search without generation', async () => {
  const {dom, w, calls} = fixture();
  try {
    await until(() => w.document.querySelector('#documents summary'));
    assert.equal(w.document.querySelector('#documents summary').textContent, 'Fixture product');
    assert.match(w.document.getElementById('status').textContent, /1 documents · 1 passages/);
    assert.equal(w.document.getElementById('generate').checked, false);
    w.document.getElementById('question').value = 'export';
    w.document.getElementById('ask-form').dispatchEvent(new w.Event('submit', {cancelable: true}));
    await until(() => w.document.querySelector('#answer-area .source'));
    assert.deepEqual(calls.find(c => c.path === '/api/ask').payload,
      {question: 'export', generate: false, mode: 'keyword'});
    assert.match(w.document.getElementById('answer-area').textContent, /No AI answer was generated/);
  } finally { dom.window.close(); }
});

test('AI drafts, safe text rendering, feedback and settings navigation work', async () => {
  const {dom, w, calls} = fixture();
  try {
    await until(() => w.document.querySelector('#documents summary'));
    const toggle = w.document.getElementById('generate'); toggle.checked = true;
    toggle.dispatchEvent(new w.Event('change'));
    w.document.getElementById('question').value = 'export';
    w.document.getElementById('ask-form').dispatchEvent(new w.Event('submit', {cancelable: true}));
    await until(() => w.document.querySelector('#answer-area .feedback button'));
    assert.equal(calls.find(c => c.path === '/api/ask').payload.mode, 'hybrid');
    assert.equal(w.document.querySelector('#answer-area img'), null);
    assert.match(w.document.getElementById('answer-area').textContent, /<img src=x/);
    w.document.querySelectorAll('#answer-area .feedback button')[1].click();
    await until(() => w.document.getElementById('queue').textContent.includes('Marked unhelpful'));
    assert.match(w.document.getElementById('answer-area').textContent, /Feedback saved/);
    w.location.hash = '#settings';
    await until(() => w.document.querySelector('#settings dd'));
    assert.equal(w.document.getElementById('faq-view').hidden, true);
    assert.equal(w.document.getElementById('settings-view').hidden, false);
    assert.match(w.document.getElementById('settings').textContent, /chat-fixture/);
    assert.match(w.document.getElementById('settings-status').textContent, /Database connected/);
  } finally { dom.window.close(); }
});

test('a failed settings query does not show a successful connection', async () => {
  const {dom, w} = fixture({failSettings: true});
  try {
    w.location.hash = '#settings';
    await until(() => w.document.getElementById('settings-status').textContent === 'Connection check failed');
    assert.match(w.document.getElementById('settings').textContent, /Database unavailable/);
    assert.equal(w.document.getElementById('settings').textContent.includes('connected'), false);
  } finally { dom.window.close(); }
});
