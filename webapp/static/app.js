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
let lastAnalysis = null; // {source_playlist_id, total_tracks, breakdown, tracks}

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

    // Reattach to an analysis still running server-side from before a
    // reload, instead of leaving the page looking idle while it finishes
    // (and instead of letting a fresh Analyse click start a duplicate run).
    let inProgress;
    try {
      inProgress = await api('/api/analyze/status');
    } catch (e) {
      inProgress = null;  // nothing has been started yet this session
    }
    if (inProgress && !inProgress.done) {
      document.getElementById('analyze-btn').disabled = true;
      setStatus(`Resuming analysis: ${inProgress.current}/${inProgress.total}...`);
      try {
        await pollAnalysis();
      } catch (e) {
        setStatus('Error: ' + e.message, true);
      } finally {
        document.getElementById('analyze-btn').disabled = false;
      }
    }
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  }
}

// ---------------------------------------------------------------- helpers

// A track's genre(s) -- at most 2, combined across all 3 sources (see
// display_genres in genre.py) so multi-source agreement decides the
// label instead of dumping every raw tag from every source. Empty when
// nothing was detected anywhere, so a track with no data just shows
// nothing rather than a "no tags found" placeholder.
function genrePills(track) {
  const genres = track.display_genres || [];
  return genres.map(g => `<span class="vote-pill matched">${g}</span>`).join('');
}

function targetOptionsHtml() {
  const sourceId = (lastAnalysis && lastAnalysis.source_playlist_id) || document.getElementById('source-select').value;
  return sourcePlaylists
    .filter(p => p.id !== sourceId)
    .map(p => `<option value="${p.id}">${p.name}</option>`)
    .join('');
}

function stateClassFor(label) {
  return label === 'Unmatched' ? 'state-none' : '';
}

// ---------------------------------------------------------------- analyze

const ANALYZE_POLL_MS = 800;

async function pollAnalysis() {
  while (true) {
    const status = await api('/api/analyze/status');
    if (!status.done) {
      setStatus(`Classifying tracks: ${status.current}/${status.total} (MusicBrainz limits lookups to 1/sec, so this can take a while)...`);
      await new Promise(r => setTimeout(r, ANALYZE_POLL_MS));
      continue;
    }
    if (status.error) {
      throw new Error(status.error);
    }
    lastAnalysis = status;
    renderBreakdown();
    setStatus(`Analyzed ${status.total_tracks} tracks.`);
    return;
  }
}

document.getElementById('analyze-btn').onclick = async () => {
  const sourceId = document.getElementById('source-select').value;
  setStatus('Fetching playlist tracks...');
  document.getElementById('analyze-btn').disabled = true;
  try {
    const started = await api('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_playlist_id: sourceId }),
    });
    setStatus(`Classifying tracks: 0/${started.total}...`);
    await pollAnalysis();
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  } finally {
    document.getElementById('analyze-btn').disabled = false;
  }
};

// -------------------------------------------------------------- breakdown

function renderBreakdown() {
  const data = lastAnalysis;
  const el = document.getElementById('breakdown-list');
  const total = data.total_tracks || 1;
  const entries = Object.entries(data.breakdown).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...entries.map(([, c]) => c), 1);

  const tracksByGenre = {};
  for (const t of data.tracks) {
    (tracksByGenre[t.genre] = tracksByGenre[t.genre] || []).push(t);
  }

  const targetOptions = targetOptionsHtml();

  el.innerHTML = entries.map(([label, count], i) => {
    const pct = Math.round((count / total) * 100);
    const uris = (tracksByGenre[label] || []).map(t => t.uri);
    return `
    <div class="bar-row" data-toggle="bd-panel-${i}">
      <div class="bar-row-top">
        <span class="bar-label"><span class="chevron">▸</span>${label}</span>
        <span class="bar-count">${count} (${pct}%)</span>
      </div>
      <div class="bar-track"><div class="bar-fill ${stateClassFor(label)}" style="width:${(count / maxCount * 100).toFixed(0)}%"></div></div>
      <div class="inline-move" data-uris='${JSON.stringify(uris)}'>
        ${moveTriggerHtml(`Move all ${count}`, targetOptions)}
        ${moveConfirmHtml(count)}
      </div>
    </div>
    <div class="track-list hidden" id="bd-panel-${i}">
      ${(tracksByGenre[label] || []).map(t => `
        <div class="track-row">
          <div class="track-info">
            <div class="track-title">${t.name} <span class="track-artist">— ${t.artist}</span></div>
            ${genrePills(t) ? `<div class="vote-row">${genrePills(t)}</div>` : ''}
          </div>
          <div class="inline-move" data-uris='${JSON.stringify([t.uri])}'>
            ${moveTriggerHtml('Move', targetOptions)}
            ${moveConfirmHtml(1)}
          </div>
        </div>
      `).join('')}
    </div>
  `;
  }).join('');

  el.querySelectorAll('.bar-row').forEach(row => {
    row.onclick = () => {
      const panel = document.getElementById(row.dataset.toggle);
      const wasHidden = panel.classList.contains('hidden');
      panel.classList.toggle('hidden');
      row.querySelector('.chevron').textContent = wasHidden ? '▾' : '▸';
    };
  });

  wireMoveControls(el);
  document.getElementById('breakdown-card').classList.remove('hidden');
}

function moveTriggerHtml(buttonLabel, targetOptions) {
  return `
    <span class="move-trigger">
      <select class="move-target">${targetOptions}</select>
      <button class="move-btn secondary">${buttonLabel}</button>
    </span>`;
}

function moveConfirmHtml(count) {
  return `
    <span class="move-confirm hidden">
      <span class="confirm-text">Move ${count} track${count === 1 ? '' : 's'} to <strong class="move-confirm-name"></strong>?</span>
      <label><input type="checkbox" class="move-remove"> remove from source</label>
      <button class="move-confirm-btn">Confirm</button>
      <button class="move-cancel-btn secondary">Cancel</button>
    </span>`;
}

function wireMoveControls(root) {
  root.querySelectorAll('.inline-move').forEach(container => {
    // Stops a click on the select/buttons from bubbling up to the
    // .bar-row's own click handler, which would otherwise also toggle
    // that genre's expand/collapse panel.
    container.addEventListener('click', (e) => e.stopPropagation());

    const trigger = container.querySelector('.move-trigger');
    const confirmBox = container.querySelector('.move-confirm');
    const targetSelect = container.querySelector('.move-target');
    const confirmName = container.querySelector('.move-confirm-name');
    const moveBtn = container.querySelector('.move-btn');
    const confirmBtn = container.querySelector('.move-confirm-btn');
    const cancelBtn = container.querySelector('.move-cancel-btn');
    const removeCheckbox = container.querySelector('.move-remove');

    moveBtn.onclick = () => {
      if (!targetSelect.value) {
        setStatus('Pick a target playlist first.', true);
        return;
      }
      confirmName.textContent = targetSelect.selectedOptions[0].textContent;
      trigger.classList.add('hidden');
      confirmBox.classList.remove('hidden');
    };

    cancelBtn.onclick = () => {
      confirmBox.classList.add('hidden');
      trigger.classList.remove('hidden');
    };

    confirmBtn.onclick = async () => {
      const uris = JSON.parse(container.dataset.uris);
      const targetId = targetSelect.value;
      const targetName = targetSelect.selectedOptions[0].textContent;
      const removeFromSource = removeCheckbox.checked;
      confirmBtn.disabled = true;
      try {
        const result = await api('/api/move', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ uris, target_playlist_id: targetId, remove_from_source: removeFromSource }),
        });
        applyMoveResult(uris);
        setStatus(`Moved ${result.added} track(s) to ${targetName}${result.removed ? ' (removed from source)' : ''}.`);
      } catch (e) {
        setStatus('Error: ' + e.message, true);
        confirmBtn.disabled = false;
      }
    };
  });
}

// Removes moved tracks from the in-memory analysis, recomputes the
// breakdown, and re-renders -- avoids a full re-analyze (and its
// MusicBrainz-throttled wait) just to reflect a move that already
// happened. Re-rendering collapses any expanded genre panels back to
// closed, which is an accepted trade-off for not hand-patching the DOM.
function applyMoveResult(movedUris) {
  const movedSet = new Set(movedUris);
  lastAnalysis.tracks = lastAnalysis.tracks.filter(t => !movedSet.has(t.uri));
  lastAnalysis.total_tracks = lastAnalysis.tracks.length;
  const breakdown = {};
  for (const t of lastAnalysis.tracks) {
    breakdown[t.genre] = (breakdown[t.genre] || 0) + 1;
  }
  lastAnalysis.breakdown = breakdown;
  renderBreakdown();
}

init();
