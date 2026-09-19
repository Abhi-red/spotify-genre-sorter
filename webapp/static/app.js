const statusEl = document.getElementById('status');
function setStatus(msg, isError) {
  statusEl.textContent = msg || '';
  statusEl.className = isError ? 'statusline error' : 'statusline';
}

async function api(path, opts) {
  const resp = await fetch(path, Object.assign({ credentials: 'same-origin' }, opts));
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${path} -> ${resp.status}: ${text}`);
  }
  return resp.json();
}

document.getElementById('connect-btn').onclick = () => {
  window.location.href = '/api/login';
};
document.getElementById('logout-btn').onclick = async () => {
  await api('/api/logout');
  window.location.reload();
};

let sourcePlaylists = [];

async function init() {
  setStatus('Checking connection...');
  try {
    const me = await api('/api/me');
    if (!me.logged_in) {
      setStatus('');
      return;
    }
    document.getElementById('connect-label').textContent = `Connected as ${me.display_name}`;
    document.getElementById('connect-btn').classList.add('hidden');
    document.getElementById('logout-btn').classList.remove('hidden');
    setStatus('Loading your playlists...');

    const data = await api('/api/playlists');
    sourcePlaylists = data.playlists;
    const select = document.getElementById('source-select');
    select.innerHTML = sourcePlaylists
      .map(p => `<option value="${p.id}">${p.name} (${p.track_count ?? '?'} tracks)</option>`)
      .join('');
    document.getElementById('source-card').classList.remove('hidden');
    setStatus(`Loaded ${sourcePlaylists.length} playlists you own.`);
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  }
}

// ---------------------------------------------------------------- helpers

const GENRE_BUCKETS = ['Pop Rock', 'EDM', 'Indie'];
const SOURCE_CODES = { spotify: 'SP', lastfm: 'LF', musicbrainz: 'MB' };

function votePills(track) {
  const votes = track.votes || {};
  return Object.entries(votes).map(([source, bucket]) => {
    const code = SOURCE_CODES[source] || source.slice(0, 2).toUpperCase();
    const cls = bucket ? 'vote-pill matched' : 'vote-pill';
    return `<span class="${cls}">${code} ${bucket || '—'}</span>`;
  }).join('');
}

function agreementMeter(track) {
  const votes = Object.values(track.votes || {}).filter(Boolean);
  const counts = {};
  votes.forEach(v => { counts[v] = (counts[v] || 0) + 1; });
  const max = Object.values(counts).reduce((a, b) => Math.max(a, b), 0);
  let segs = '';
  for (let i = 0; i < 3; i++) {
    segs += `<span class="meter-seg${i < max ? ' filled' : ''}"></span>`;
  }
  return `<span class="meter" title="${max} of 3 sources agree">${segs}</span>`;
}

function confidenceBadge(track) {
  if (track.confidence === 'high') return '<span class="confidence-badge high">High confidence</span>';
  if (track.confidence === 'low') return '<span class="confidence-badge low">Needs review</span>';
  return '<span class="confidence-badge none">No match</span>';
}

// ---------------------------------------------------------------- analyze

document.getElementById('analyze-btn').onclick = async () => {
  const sourceId = document.getElementById('source-select').value;
  setStatus('Fetching tracks and voting on genres (this can take a while on large playlists -- MusicBrainz limits lookups to 1/sec)...');
  document.getElementById('analyze-btn').disabled = true;
  try {
    const data = await api('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_playlist_id: sourceId }),
    });
    renderBreakdown(data);
    setStatus(`Analyzed ${data.total_tracks} tracks.`);
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  } finally {
    document.getElementById('analyze-btn').disabled = false;
  }
};

function stateClassFor(label) {
  if (label === 'Needs Review') return 'state-review';
  if (label === 'Unmatched') return 'state-none';
  return '';
}

function renderBreakdown(data) {
  const el = document.getElementById('breakdown-list');
  const entries = Object.entries(data.breakdown).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...entries.map(([, c]) => c), 1);

  const tracksByGenre = {};
  for (const t of data.tracks) {
    (tracksByGenre[t.genre] = tracksByGenre[t.genre] || []).push(t);
  }

  el.innerHTML = entries.map(([label, count], i) => `
    <div class="bar-row" data-toggle="bd-panel-${i}">
      <div class="bar-row-top">
        <span class="bar-label"><span class="chevron">▸</span>${label}</span>
        <span class="bar-count">${count}</span>
      </div>
      <div class="bar-track"><div class="bar-fill ${stateClassFor(label)}" style="width:${(count / maxCount * 100).toFixed(0)}%"></div></div>
    </div>
    <div class="track-list hidden" id="bd-panel-${i}">
      ${(tracksByGenre[label] || []).map(t => `<div>${t.name} <span class="muted">— ${t.artist}</span> ${votePills(t)}</div>`).join('')}
    </div>
  `).join('');

  el.querySelectorAll('.bar-row').forEach(row => {
    row.onclick = () => {
      const panel = document.getElementById(row.dataset.toggle);
      const wasHidden = panel.classList.contains('hidden');
      panel.classList.toggle('hidden');
      row.querySelector('.chevron').textContent = wasHidden ? '▾' : '▸';
    };
  });

  document.getElementById('breakdown-card').classList.remove('hidden');
  renderReview(data);
  renderMapping(data);
}

// ------------------------------------------------------------------ review

function renderReview(data) {
  const el = document.getElementById('review-list');
  const reviewTracks = data.tracks.filter(t => t.genre === 'Needs Review');
  const card = document.getElementById('review-card');

  if (reviewTracks.length === 0) {
    card.classList.add('hidden');
    el.innerHTML = '';
    return;
  }

  const resolveOptions = '<option value="">Leave for now</option>' +
    GENRE_BUCKETS.map(b => `<option value="${b}">${b}</option>`).join('') +
    '<option value="Unmatched">Mark unmatched</option>';

  el.innerHTML = reviewTracks.map(t => `
    <div class="track-row">
      <div class="track-info">
        <div class="track-title">${t.name} <span class="track-artist">— ${t.artist}</span></div>
        <div class="vote-row">${votePills(t)}${agreementMeter(t)}</div>
      </div>
      <select class="resolve-select" data-uri="${t.uri}">${resolveOptions}</select>
    </div>
  `).join('');

  card.classList.remove('hidden');
}

document.getElementById('save-review-btn').onclick = async () => {
  const selects = document.querySelectorAll('#review-list select[data-uri]');
  const resolutions = {};
  selects.forEach(sel => {
    if (sel.value) resolutions[sel.dataset.uri] = sel.value;
  });
  if (Object.keys(resolutions).length === 0) {
    setStatus('No review choices selected.');
    return;
  }
  setStatus('Saving review choices...');
  try {
    const data = await api('/api/resolve_review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resolutions }),
    });
    renderBreakdown(data);
    setStatus('Review choices saved.');
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  }
};

// ----------------------------------------------------------------- mapping

function renderMapping(data) {
  const sourceId = document.getElementById('source-select').value;
  const targetOptions = sourcePlaylists.filter(p => p.id !== sourceId);
  const optionsHtml = '<option value="">Don\'t sort</option>' +
    targetOptions.map(p => `<option value="${p.id}">${p.name}</option>`).join('');

  const entries = Object.entries(data.breakdown).sort((a, b) => b[1] - a[1]);
  const el = document.getElementById('mapping-list');
  el.innerHTML = entries
    .filter(([label]) => label !== 'Unmatched' && label !== 'Needs Review')
    .map(([label, count]) => `
      <div class="map-row">
        <span class="row-label">${label} <span class="row-count">${count}</span></span>
        <select data-genre="${label}">${optionsHtml}</select>
      </div>
    `).join('');
  if (data.breakdown['Needs Review']) {
    el.innerHTML += `<div class="row-note">Needs Review (${data.breakdown['Needs Review']}) — resolve these above before they can be sorted</div>`;
  }
  if (data.breakdown['Unmatched']) {
    el.innerHTML += `<div class="row-note">Unmatched (${data.breakdown['Unmatched']}) — no genre signal, always left alone</div>`;
  }
  document.getElementById('mapping-card').classList.remove('hidden');
  document.getElementById('preview-card').classList.add('hidden');
  document.getElementById('result-card').classList.add('hidden');
}

document.getElementById('preview-btn').onclick = async () => {
  const selects = document.querySelectorAll('#mapping-list select[data-genre]');
  const mapping = {};
  selects.forEach(sel => {
    if (sel.value) mapping[sel.dataset.genre] = sel.value;
  });
  setStatus('Building preview...');
  try {
    const data = await api('/api/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mapping }),
    });
    renderPreview(data);
    setStatus('Preview ready. Nothing written to Spotify yet.');
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  }
};

function renderPreview(data) {
  const el = document.getElementById('preview-list');
  let html = '';
  if (data.targets.length === 0) {
    html += '<p class="muted">No genres mapped to a target playlist -- nothing would be added anywhere.</p>';
  }
  for (const target of data.targets) {
    html += `<div class="preview-group"><h3>${target.playlist_name} <span class="preview-count">+${target.count}</span></h3>`;
    html += '<div class="track-list">' + target.tracks.map(t => `<div>${t.name} <span class="muted">— ${t.artist}</span> <span class="track-tag">${t.genre}</span></div>`).join('') + '</div></div>';
  }
  html += `<div class="preview-group"><h3>Not moving <span class="preview-count">${data.unmapped_count}</span></h3>`;
  html += '<div class="track-list">' + data.unmapped.map(t => `<div>${t.name} <span class="muted">— ${t.artist}</span> <span class="track-tag">${t.genre}</span></div>`).join('') + '</div></div>';
  el.innerHTML = html;
  document.getElementById('preview-card').classList.remove('hidden');
}

document.getElementById('confirm-btn').onclick = async () => {
  const removeFromSource = document.getElementById('remove-from-source').checked;
  const confirmBtn = document.getElementById('confirm-btn');
  confirmBtn.disabled = true;
  setStatus('Applying changes to Spotify...');
  try {
    const data = await api('/api/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ remove_from_source: removeFromSource }),
    });
    renderResult(data);
    setStatus('Done.');
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  } finally {
    confirmBtn.disabled = false;
  }
};

function renderResult(data) {
  const el = document.getElementById('result-list');
  let html = '';
  for (const r of data.results) {
    html += `<li>Added ${r.added} track(s) to <strong>${r.playlist_name}</strong></li>`;
  }
  if (data.removed_from_source) {
    html += `<li>Removed ${data.removed_from_source} track(s) from the source playlist (move mode)</li>`;
  } else {
    html += `<li>Source playlist left untouched (copy mode)</li>`;
  }
  html += `<li>${data.unmapped_left_in_place} track(s) left unsorted, untouched</li>`;
  el.innerHTML = html;
  document.getElementById('result-card').classList.remove('hidden');
}

init();
