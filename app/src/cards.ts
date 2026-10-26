/** Per-room "living report" cards: interval bands, night listen, and "What we couldn't see". */
import { METRICS, type MetricDef } from './compare';
import { roomName, type Interval, type LoadedReport, type Report, type Room, type UnseenItem } from './data/schema';
import { h } from './dom';
import { scalePct } from './geo';

export const AUDIO_LABEL = 'Illustrative synthesis, not a recording';

const fmt = (v: number, unit: string) => `${unit === 'h/day' ? v.toFixed(1) : v.toFixed(unit === '°C' ? 1 : 0)}`;

export function intervalText(iv: Interval, unit: string): string {
  return `${fmt(iv.pred, unit)} ${unit} (90 % interval ${fmt(iv.lo, unit)}–${fmt(iv.hi, unit)})`;
}

/** Pred dot + lo–hi bar on the metric's fixed scale. */
export function band(def: MetricDef, iv: Interval): HTMLElement {
  const lo = scalePct(iv.lo, def.min, def.max);
  const hi = scalePct(iv.hi, def.min, def.max);
  const p = scalePct(iv.pred, def.min, def.max);
  const clipped = iv.lo < def.min || iv.hi > def.max;
  return h('div', { class: 'band', role: 'img', 'aria-label': `${def.label}: ${intervalText(iv, def.unit)}` },
    h('div', { class: 'band-track' },
      h('div', { class: 'band-bar', style: `left:${lo}%;width:${Math.max(hi - lo, 0.8)}%` }),
      h('div', { class: 'band-dot', style: `left:${p}%` })),
    h('div', { class: 'band-scale', 'aria-hidden': 'true' },
      h('span', {}, `${def.min}`), clipped ? h('span', { class: 'clip' }, 'interval extends beyond scale') : null,
      h('span', {}, `${def.max} ${def.unit}`)));
}

function metricRow(def: MetricDef, iv: Interval | undefined): HTMLElement {
  return h('div', { class: 'metric' },
    h('div', { class: 'metric-head' },
      h('span', { class: 'metric-label' }, def.label),
      h('span', { class: 'metric-value' }, iv ? intervalText(iv, def.unit) : 'not estimated')),
    iv ? band(def, iv) : null);
}

// ---- night listen ---------------------------------------------------------------------------
let current: { audio: HTMLAudioElement; button: HTMLButtonElement } | null = null;

export function stopAudio(): void {
  if (!current) return;
  current.audio.pause();
  current.button.textContent = current.button.dataset.idle ?? 'Play';
  current.button.setAttribute('aria-pressed', 'false');
  current = null;
}

function playButton(label: string, url: string): HTMLButtonElement {
  const btn = h('button', { type: 'button', class: 'btn small', 'aria-pressed': 'false', 'data-idle': `▶ ${label}` }, `▶ ${label}`);
  btn.addEventListener('click', () => {
    if (current?.button === btn) return stopAudio();
    stopAudio();
    const audio = new Audio(url);
    current = { audio, button: btn };
    btn.textContent = `■ Stop (${label})`;
    btn.setAttribute('aria-pressed', 'true');
    audio.addEventListener('ended', () => { if (current?.audio === audio) stopAudio(); });
    audio.play().catch(() => {
      stopAudio();
      btn.textContent = `${label}: audio unavailable`;
    });
  });
  return btn;
}

function nightListen(loaded: LoadedReport, room: Room): HTMLElement | null {
  const ref = loaded.report.noise.audio?.[room.id];
  if (!ref) return null;
  const body = loaded.baseUrl
    ? h('div', { class: 'row' }, playButton('Windows closed', loaded.baseUrl + ref.closed), playButton('Window ajar', loaded.baseUrl + ref.open))
    : h('p', { class: 'muted' }, 'Audio is only available for reports served from the reports folder, not for a locally opened file.');
  return h('div', { class: 'listen' },
    h('h4', {}, 'Night listen (02:00)'),
    body,
    h('p', { class: 'audio-label' }, AUDIO_LABEL));
}

// ---- what we couldn't see ---------------------------------------------------------------------
const pct = (v: number) => `${Math.round(v * 100)} %`;

function unseenItem(item: UnseenItem): HTMLElement {
  const post = Object.entries(item.posterior).sort((a, b) => b[1] - a[1]);
  const share = Object.entries(item.variance_share ?? {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  return h('li', { class: 'unseen' },
    h('div', { class: 'unseen-prop' }, item.property.replace(/_/g, ' ')),
    h('ul', { class: 'post', 'aria-label': `Our belief about ${item.property}` },
      ...post.map(([k, v]) => h('li', {},
        h('span', { class: 'post-k' }, k.replace(/_/g, ' ')),
        h('span', { class: 'post-bar', 'aria-hidden': 'true' }, h('span', { style: `width:${scalePct(v, 0, 1)}%` })),
        h('span', { class: 'post-v' }, pct(v))))),
    share.length
      ? h('p', { class: 'muted' }, 'Share of the uncertainty it causes: ' + share.map(([k, v]) => `${k} ${pct(v)}`).join(', '))
      : null,
    h('p', {}, item.explanation));
}

function unseenSection(r: Report, room: Room): HTMLElement | null {
  const items = r.uncertainty?.[room.id]?.what_we_couldnt_see ?? [];
  if (!items.length) return null;
  return h('details', { class: 'unseen-box' },
    h('summary', {}, `What we couldn't see (${items.length})`),
    h('ul', { class: 'unseen-list' }, ...items.map(unseenItem)));
}

// ---- card -------------------------------------------------------------------------------------
export function roomCard(loaded: LoadedReport, room: Room): HTMLElement {
  const r = loaded.report;
  const noise = r.noise.rooms[room.id];
  const heat = r.heat.rooms[room.id];
  const rows = METRICS.map((m) => metricRow(m, m.get(r, room.id)));
  const extras: string[] = [];
  if (heat?.hours_above_26_typical_summer !== undefined) extras.push(`${Math.round(heat.hours_above_26_typical_summer)} h above 26 °C`);
  if (heat?.hours_above_28_typical_summer !== undefined) extras.push(`${Math.round(heat.hours_above_28_typical_summer)} h above 28 °C`);
  const attribution = noise?.attribution_db ? Object.entries(noise.attribution_db).sort((a, b) => b[1] - a[1]) : [];
  return h('article', { class: 'card', 'data-room': room.id },
    h('h3', {}, roomName(room), h('span', { class: 'kind' }, room.kind.replace(/_/g, ' '))),
    ...rows.slice(0, 2),
    h('div', { class: 'group' }, ...rows.slice(2, 4),
      attribution.length
        ? h('p', { class: 'muted' }, 'Indoor night level by source: ' + attribution.map(([k, v]) => `${k} ${v.toFixed(0)} dB(A)`).join(', '))
        : null,
      noise?.who_guideline_note ? h('p', { class: 'who-note' }, noise.who_guideline_note) : null),
    h('div', { class: 'group' }, ...rows.slice(4),
      extras.length ? h('p', { class: 'muted' }, `Typical summer: ${extras.join(', ')}`) : null),
    nightListen(loaded, room),
    unseenSection(r, room));
}

export function roomCards(loaded: LoadedReport): HTMLElement {
  return h('div', { class: 'cards' }, ...loaded.report.geometry.rooms.map((room) => roomCard(loaded, room)));
}
