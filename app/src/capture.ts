/**
 * Guided 2-minute walkthrough capture. Everything stays on the device: the video and a JSON
 * sidecar (prompt timestamps + compass readings) are offered as local downloads. No uploads.
 */
import { clear, h } from './dom';

export interface Step { id: string; prompt: string; seconds: number; window?: boolean }

export const STEPS: Step[] = [
  { id: 'entrance', prompt: 'Start at the entrance. Hold the phone in landscape at chest height.', seconds: 15 },
  { id: 'windows', prompt: 'Pan slowly across each window — frame, glass, sill, balcony. Tap “Mark window” while facing each one.', seconds: 45, window: true },
  { id: 'view', prompt: 'Tilt to show the view outside each window (sky, neighbouring buildings, street).', seconds: 20, window: true },
  { id: 'rooms', prompt: 'Show a door and the ceiling corner in each room.', seconds: 40 },
];
export const TOTAL_SECONDS = STEPS.reduce((s, x) => s + x.seconds, 0);

export interface CompassReading { t_s: number; step: string; heading_deg: number | null; source: string; marked: boolean }
export interface Sidecar {
  schema: 'dwell-walkthrough/1';
  started_utc: string;
  duration_s: number;
  mime_type: string;
  user_agent: string;
  steps: { id: string; prompt: string; t_start_s: number }[];
  compass: CompassReading[];
  note: string;
}

/** Heading in degrees clockwise from (magnetic) north, or null if the event can't provide one. */
export function headingFromEvent(e: { alpha: number | null; absolute?: boolean; webkitCompassHeading?: number }): { heading: number | null; source: string } {
  if (typeof e.webkitCompassHeading === 'number' && Number.isFinite(e.webkitCompassHeading)) {
    return { heading: e.webkitCompassHeading, source: 'webkitCompassHeading' };
  }
  if (e.absolute && typeof e.alpha === 'number') return { heading: (360 - e.alpha) % 360, source: 'absolute-alpha' };
  return { heading: null, source: 'unavailable' };
}

export function pickMimeType(isSupported: (t: string) => boolean): string {
  const candidates = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
  return candidates.find((t) => isSupported(t)) ?? '';
}

export function fileStamp(d: Date): string {
  return d.toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
}

function download(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = h('a', { href: url, download: name });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

type OrientationCtor = typeof DeviceOrientationEvent & { requestPermission?: () => Promise<'granted' | 'denied'> };

export function mountCapture(root: HTMLElement): () => void {
  clear(root);
  let stream: MediaStream | null = null;
  let recorder: MediaRecorder | null = null;
  let chunks: Blob[] = [];
  let t0 = 0;
  let startedAt = new Date();
  let stepIdx = -1;
  let stepStarts: Sidecar['steps'] = [];
  let compass: CompassReading[] = [];
  let lastHeading: { heading: number | null; source: string } = { heading: null, source: 'unavailable' };
  let timer = 0;
  let sampler = 0;
  let orientationOn = false;

  const video = h('video', { class: 'preview', muted: true, playsinline: true, autoplay: true, 'aria-label': 'Camera preview' });
  const clock = h('div', { class: 'clock', 'aria-live': 'off' }, `0:00 / ${Math.floor(TOTAL_SECONDS / 60)}:00`);
  const prompt = h('p', { class: 'prompt', 'aria-live': 'polite' }, 'Press “Start camera” to begin. Recording only starts when you press “Record”.');
  const compassOut = h('div', { class: 'compass', 'aria-live': 'off' }, 'Compass: not enabled');
  const status = h('p', { class: 'muted', role: 'status' });
  const btnCam = h('button', { type: 'button', class: 'btn' }, 'Start camera');
  const btnCompass = h('button', { type: 'button', class: 'btn' }, 'Enable compass');
  const btnRec = h('button', { type: 'button', class: 'btn primary', disabled: true }, '● Record');
  const btnNext = h('button', { type: 'button', class: 'btn', disabled: true }, 'Next step');
  const btnMark = h('button', { type: 'button', class: 'btn', disabled: true }, 'Mark window');
  const btnStop = h('button', { type: 'button', class: 'btn danger', disabled: true }, '■ Stop & save');
  const stepList = h('ol', { class: 'steps' }, ...STEPS.map((s) => h('li', { 'data-step': s.id }, s.prompt)));
  const landscapeHint = h('p', { class: 'hint' }, 'Tip: rotate the phone to landscape.');

  root.append(
    h('section', { class: 'panel privacy', 'aria-label': 'Privacy' },
      h('h2', {}, 'Capture a walkthrough'),
      h('p', {}, h('strong', {}, 'Nothing is uploaded. '),
        'The video and a small JSON file of prompt times and compass readings are saved only to this device as downloads. '
        + 'Please avoid filming people, documents and screens.')),
    h('div', { class: 'capture-grid' },
      h('div', { class: 'preview-wrap' }, video, clock, landscapeHint),
      h('div', { class: 'capture-side' }, prompt, compassOut,
        h('div', { class: 'row wrap' }, btnCam, btnCompass),
        h('div', { class: 'row wrap' }, btnRec, btnNext, btnMark, btnStop),
        status, stepList)),
  );

  const updateLandscape = () => { landscapeHint.hidden = window.innerWidth >= window.innerHeight; };
  window.addEventListener('resize', updateLandscape);
  updateLandscape();

  const now = () => (performance.now() - t0) / 1000;
  const onOrientation = (e: DeviceOrientationEvent) => {
    const next = headingFromEvent(e as DeviceOrientationEvent & { webkitCompassHeading?: number });
    // Android fires both a relative and an absolute event; never let the relative one erase a real heading
    if (next.heading === null && lastHeading.heading !== null) return;
    lastHeading = next;
    compassOut.textContent = lastHeading.heading === null
      ? 'Compass: no absolute heading from this device'
      : `Compass: ${Math.round(lastHeading.heading)}° (${lastHeading.source})`;
  };
  const logCompass = (marked: boolean) => {
    if (stepIdx < 0) return;
    compass.push({ t_s: +now().toFixed(2), step: STEPS[stepIdx].id, heading_deg: lastHeading.heading, source: lastHeading.source, marked });
  };

  const setStep = (i: number) => {
    stepIdx = i;
    stepStarts.push({ id: STEPS[i].id, prompt: STEPS[i].prompt, t_start_s: +now().toFixed(2) });
    prompt.textContent = `Step ${i + 1}/${STEPS.length}: ${STEPS[i].prompt}`;
    stepList.querySelectorAll('li').forEach((li, j) => li.classList.toggle('active', j === i));
    btnMark.disabled = !STEPS[i].window;
    btnNext.disabled = i >= STEPS.length - 1;
  };

  btnCam.addEventListener('click', async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      status.textContent = 'This browser cannot access the camera (needs HTTPS or localhost).';
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false,
      });
      video.srcObject = stream;
      btnRec.disabled = false;
      btnCam.disabled = true;
      status.textContent = 'Camera ready (rear camera if available). Audio is not recorded.';
      const orient = screen.orientation as ScreenOrientation & { lock?: (o: string) => Promise<void> };
      orient?.lock?.('landscape').catch(() => undefined);
    } catch (err) {
      status.textContent = `Camera unavailable: ${(err as Error).message}`;
    }
  });

  btnCompass.addEventListener('click', async () => {
    if (typeof DeviceOrientationEvent === 'undefined') {
      compassOut.textContent = 'Compass: not available in this browser';
      return;
    }
    const Ctor = DeviceOrientationEvent as OrientationCtor;
    try {
      if (typeof Ctor.requestPermission === 'function' && (await Ctor.requestPermission()) !== 'granted') {
        compassOut.textContent = 'Compass: permission denied';
        return;
      }
    } catch {
      compassOut.textContent = 'Compass: permission request failed';
      return;
    }
    if (!orientationOn) {
      window.addEventListener('deviceorientationabsolute', onOrientation as EventListener);
      window.addEventListener('deviceorientation', onOrientation);
      orientationOn = true;
    }
    compassOut.textContent = 'Compass: waiting for readings…';
    btnCompass.disabled = true;
  });

  btnRec.addEventListener('click', () => {
    if (!stream) return;
    if (typeof MediaRecorder === 'undefined') {
      status.textContent = 'This browser cannot record video (MediaRecorder missing).';
      return;
    }
    const mime = pickMimeType((t) => MediaRecorder.isTypeSupported(t));
    recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    chunks = [];
    stepStarts = [];
    compass = [];
    recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    recorder.onstop = () => save(recorder?.mimeType || mime || 'video/webm');
    t0 = performance.now();
    startedAt = new Date();
    recorder.start(1000);
    setStep(0);
    btnRec.disabled = true;
    btnStop.disabled = false;
    timer = window.setInterval(() => {
      const t = now();
      clock.textContent = `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')} / ${Math.floor(TOTAL_SECONDS / 60)}:00`;
      clock.classList.toggle('over', t > TOTAL_SECONDS);
      // auto-advance on the guide schedule (the user can also skip ahead with "Next step")
      let acc = 0;
      const due = STEPS.findIndex((s) => (acc += s.seconds) > t);
      if (due > stepIdx) setStep(due);
    }, 250);
    // log heading once a second during window steps
    sampler = window.setInterval(() => { if (STEPS[stepIdx]?.window) logCompass(false); }, 1000);
  });

  btnNext.addEventListener('click', () => { if (stepIdx < STEPS.length - 1) setStep(stepIdx + 1); });
  btnMark.addEventListener('click', () => {
    logCompass(true);
    status.textContent = `Window marked at ${lastHeading.heading === null ? 'unknown heading' : Math.round(lastHeading.heading) + '°'}.`;
  });
  btnStop.addEventListener('click', () => {
    if (recorder?.state === 'recording') recorder.stop();
    btnStop.disabled = true;
  });

  function save(mime: string) {
    window.clearInterval(timer);
    window.clearInterval(sampler);
    const stamp = fileStamp(startedAt);
    const ext = mime.includes('mp4') ? 'mp4' : 'webm';
    const sidecar: Sidecar = {
      schema: 'dwell-walkthrough/1', started_utc: startedAt.toISOString(), duration_s: +now().toFixed(2), mime_type: mime,
      user_agent: navigator.userAgent, steps: stepStarts, compass,
      note: 'Compass headings are device-reported (often magnetic north, uncorrected) and may be unavailable or noisy.',
    };
    download(new Blob(chunks, { type: mime }), `dwell_walkthrough_${stamp}.${ext}`);
    download(new Blob([JSON.stringify(sidecar, null, 2)], { type: 'application/json' }), `dwell_walkthrough_${stamp}.json`);
    status.textContent = `Saved locally as dwell_walkthrough_${stamp}.${ext} + .json (check your downloads).`;
    prompt.textContent = 'Done. You can record again.';
    btnRec.disabled = !stream;
    btnNext.disabled = true;
    btnMark.disabled = true;
    stepIdx = -1;
  }

  return () => {
    window.clearInterval(timer);
    window.clearInterval(sampler);
    if (recorder?.state === 'recording') recorder.stop();
    stream?.getTracks().forEach((t) => t.stop());
    window.removeEventListener('resize', updateLandscape);
    window.removeEventListener('deviceorientationabsolute', onOrientation as EventListener);
    window.removeEventListener('deviceorientation', onOrientation);
  };
}
