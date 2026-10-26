# DEMO — 2-minute live script

Setup (once, before the demo): `make demo` (trains on the synthetic world if needed, generates three
reports, builds the app), then `cd app && npm run dev -- --host` and open the printed URL on a laptop
and, optionally, a phone on the same Wi-Fi.

**0:00 — The question.** "Before you sign a lease you see a place for ten minutes, at noon, in whatever
season it is. Dwell asks: from a two-minute phone walkthrough plus public map data, can we predict what
living there is like — winter sun in each room, night-time noise, summer heat — with honest error bars?"

**0:15 — Capture.** Open the *Capture* tab on the phone. Show the guided prompts ("pan slowly across each
window — frame, glass, sill, balcony"), the compass reading logged at each window, and the privacy note:
the video is saved on the device only; nothing is uploaded. (Don't record the audience.)

**0:35 — Report.** Back on the laptop, pick the hypothetical unit on real Toronto geodata (Queen &
Spadina). Point out: the SYNTHETIC/hypothetical badge, the disclaimer banner (estimates, not an inspection),
the 3D view built from OSM + City of Toronto 3D massing.

**0:50 — Time slider.** Set the date to the winter solstice and drag the hour slider: the sun patch moves
across the bedroom floor and disappears behind the building across the street. Switch to the summer
solstice to contrast.

**1:10 — Night listen.** On the bedroom card press *Night listen — windows closed*, then *window ajar*.
Say explicitly: "This is an illustrative synthesis from the predicted spectrum — not a recording." Point at
the source attribution (road vs streetcar).

**1:25 — What we couldn't see.** Open the uncertainty section: glazing posterior (single/double/triple),
and the share of noise/heat uncertainty each hidden property explains. "This is why the interval is wide —
and what you could ask the landlord to narrow it."

**1:40 — Compare.** Compare mode: the busy-street synthetic unit vs the quiet one. The summary says which is
quieter/sunnier/cooler and whether the difference exceeds the uncertainty ("too close to call" otherwise).

**1:55 — Honest status.** "All accuracy numbers so far are on a synthetic world; real-home validation with
in-home sensors is the next step — the firmware, protocol and analysis are ready." (Point to README's
accuracy table, every number of which links to a results file.)
