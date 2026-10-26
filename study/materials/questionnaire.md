# Dwell decision study: questionnaire items (v1.0)

`questionnaire.json` in this folder holds the same items in machine-readable form. Each item names the
CSV column its answer goes into (see `study/README.md`, "Data formats"). Read every item aloud exactly
as written, or show it on screen.

## Part 1: Preferences (before any unit is shown) → `participants.csv`

**1a. Points (100 in total, steps of 5).**
> Imagine you are choosing your next apartment and everything else (rent, size, location, layout) is
> equal. Split 100 points across these three qualities according to how much each matters to you. More
> points = more important. You may give 0 to a quality you do not care about.

| Quality | Column |
|---|---|
| Quiet at night in the bedroom (little traffic / street / transit noise) | `w_quiet` |
| Direct sunlight in the living room in winter | `w_sunny` |
| Staying cool on hot summer days (lower indoor peak temperature) | `w_cool` |

**1b. Forced ranking (1 = most important, no ties).** → `rank_quiet`, `rank_sunny`, `rank_cool`
> Now rank the same three qualities from most important (1) to least important (3).

If the ranking contradicts the points (a lower-ranked quality got strictly more points), ask once:
"Your points and ranking disagree. Which one reflects your view?" Correct the one the participant
picks and write `points/rank corrected` in `notes`. If two qualities got equal points, the ranking
breaks the tie in the analysis.

## Part 2: Per pair (K times) → `responses.csv`

**2a. Choice.** → `chosen_unit` (enter the unit ID, `unit_a` or `unit_b` from the schedule)
> If these were the only two options at the same rent, which apartment would you choose to live in?
> (Apartment A was shown first, Apartment B second.)

**2b. Confidence (1–7).** → `confidence`
> How confident are you that this apartment would actually suit you better on the qualities you care
> about? 1 = not at all confident, 4 = moderately confident, 7 = completely confident.

**2c. Probability probe (only when the schedule says `probe = True`, which is every report trial).**
→ `probe_p_a` (0–100) and `probe_dim` (copy it from the schedule)

| `probe_dim` | Wording |
|---|---|
| quiet | What is the probability (0–100 %) that Apartment A's bedroom is **quieter** at night than Apartment B's? |
| sunny | What is the probability (0–100 %) that Apartment A's living room gets **more direct winter sun** than Apartment B's? |
| cool  | What is the probability (0–100 %) that Apartment A **stays cooler** on hot summer days than Apartment B? |

Help text: "50 % means 'no idea / equally likely', 100 % means you are certain A is, 0 % means you are
certain B is. Steps of 5 are fine."

## Part 3: End of session → `participants.csv`

Scale: 1 = strongly disagree … 7 = strongly agree. `trust_3` is reverse-keyed; the analysis reverses it.

| Column | Construct | Statement |
|---|---|---|
| `useful_1` | usefulness | The Dwell reports helped me compare the apartments on the qualities I care about. |
| `useful_2` | usefulness | I would want a report like this before signing a lease. |
| `useful_3` | usefulness | The reports told me things I could not have judged from the video tour. |
| `trust_1` | trust | I trusted the numbers in the Dwell reports. |
| `trust_2` | trust | I understood what the ranges (intervals) in the reports meant. |
| `trust_3` | trust (reverse) | I would want to double-check everything the report said before relying on it. |
| `trust_4` | trust | When the ranges of two apartments overlapped, I relied on the report less. |

**Attention check** → `attention_pass` (TRUE if the answer is correct)
> To show you are reading carefully, please select "Somewhat disagree" for this statement.

**Recognition** → `knows_a_unit` (TRUE means the participant is excluded)
> Did you recognise any of the apartments, or do you know someone who lives in one of them?

**Comments (optional)** → `notes`
> Anything else you'd like to tell us about the reports or the apartments? (Please don't include names
> or addresses.)
