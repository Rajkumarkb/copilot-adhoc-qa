# AlertBus event processing: watching videos and processing an event like a human reviewer

Page: `qa-alertbus-processing.aws.buspatrol.com/process/<eventId>` (Event Processing > Q.A. Processable Events > open event).
Header row: Date & Time | Vehicle | Partner | Location | Violations | Reviewer. Wizard tabs: **Choose Images → Choose Videos → Citation Details → Finish Processing**.

Viewing a frame = `browser_take_screenshot` WITHOUT `filename` (the image is shown to you). Save evidence only WITH `filename`.
Budget: at most 35 viewing screenshots per event. Never write a full plate, owner name or address into notes, defects or the model.
Only process events you claimed yourself from **Q.A. Processable Events** in this run (record them as OWNED). Never grab, submit or finish an event from the regular Processable Events queue or one assigned to someone else.

## Browser snippets (pass to `browser_evaluate` as `function`; replace I and T)
LIST - all videos; the biggest one is the MAIN player, the rest are camera tiles
```
() => [...document.querySelectorAll('video')].map((v,i)=>{const r=v.getBoundingClientRect();return {i, w:Math.round(r.width), h:Math.round(r.height), label:((v.closest('div')||v).innerText||'').split('\n').filter(Boolean).pop()||'', duration:Math.round(v.duration*10)/10, t:Math.round(v.currentTime*10)/10, paused:v.paused, ready:v.readyState, error:!!v.error}})
```
FOCUS - pause video I at T seconds and show it full-window (your zoom)
```
async () => { const v=document.querySelectorAll('video')[I]; v.muted=true; v.pause(); if (v.readyState<1) await new Promise(r=>v.addEventListener('loadedmetadata',r,{once:true})); v.currentTime=T; await new Promise(r=>v.addEventListener('seeked',r,{once:true})); if (v.dataset.qaStyle===undefined) v.dataset.qaStyle=v.getAttribute('style')||''; v.setAttribute('style','position:fixed;inset:0;width:100vw;height:100vh;object-fit:contain;background:#000;z-index:2147483647'); return {t:v.currentTime, duration:v.duration}; }
```
RESTORE - put videos back (ALWAYS before clicking any app button; the video stays paused at the same time)
```
() => document.querySelectorAll('video').forEach(v=>{ if (v.dataset.qaStyle!==undefined){ v.setAttribute('style', v.dataset.qaStyle); delete v.dataset.qaStyle; } })
```

## Step 0 - Claim an event
1. Go to **Q.A. Processable Events** and claim/open one event (at most `self_created_data.max_per_run` per run).
2. Confirm the banner says you are assigned to process it, then `python3 qa/ledger.py note obs "OWNED event <eventId>"`.

## Step 1 - Choose Images (find the VIOLATING vehicle, not just any vehicle)
A violation = a vehicle that MOVES past the stopped bus WHILE its red lights / stop arm are active. Parked cars and cars that
passed before the red lights came on are NOT violators, even if their plate is the clearest one on screen.

1. Tiles: the left grid shows camera tiles (overview, windshield, inner lane, outer lane, ...). Skip "Failed to load video" / "missing" tiles (note once with `note obs`). The tile marked "Selected" plays in the main player.
2. Load a usable **overview** tile into the main player. Run LIST and pick the MAIN player (largest w×h).
3. Find the red window: the overlay has a coloured light indicator next to the channel (top-left dot: yellow/amber = warning lights, RED = red lights / stop arm out); the bus's red STOP sign also shows at the frame edge. Coarse-scan 6 frames, then narrow down (halve the interval) to the FIRST frame where the indicator is red = T_red, and the frame where it goes off = T_off (or the end of the video).
4. List the parked/static vehicles: view a frame ~2 s BEFORE T_red and the frame at T_red. Every vehicle that is at the same place (same spot relative to houses, trees, kerb) in both is parked/static: note them (e.g. "white sedan at kerb right, silver hatchback behind it") and EXCLUDE them for the rest of the event.
5. Find the mover: view frames every 0.5 s from T_red to T_off. The violator is a vehicle whose position changes from frame to frame (gets closer/farther, crosses the frame, passes the bus/stop arm) during the red window. If several move, pick the one that passes the bus; if none moves, there is no violation on this camera: check the next camera at the same overlay time, and if still none, do NOT grab: `note ambiguity "no moving vehicle during red window, event <id>"` and use the disapproval path.
6. Track the same vehicle on other cameras by matching the OVERLAY date/time (not the video offset) and its colour/type, e.g. windshield or inner lane for the plate and rear.
7. Choose the three frames, all showing THE violator:
   - **Overview**: violator beside/passing the bus WITH the red indicator / stop arm visible in the same frame.
   - **License Plate**: the violator's plate largest and sharpest (any camera, during or just after the red window).
   - **Rearview**: the violator from behind after passing.
8. Before each grab write one line: `python3 qa/ledger.py note obs "VIOLATOR <colour/type>, moving <direction> at overlay <time>, red indicator <on/off>; excluded parked: <list>"`. If you can't fill it in honestly, don't grab.
9. FOCUS to the chosen time → view → RESTORE → click **Grab Overview / Grab License Plate / Grab Rearview**. A grab already made on the wrong vehicle must be redone (grab again on the right frame; check the tile badge moves).
10. **Crop License Plate** dialog (after Grab License Plate): shrink the crop box tightly around the violator's plate (drag the box handles with `browser_drag`, or the mouse tools if available), check "New Image Preview" shows the plate filling most of the image and belonging to the violator, then **Save**. If the crop can't be adjusted, `note obs` and Save the default.
11. Read the plate characters and state from the violator only. Accept only if every character is clearly legible in at least two frames; otherwise don't guess: `note ambiguity "plate not legible, event <id>"` and use the disapproval path.

## Step 2 - Choose Videos (attach the evidence clips)
1. The top shows 3 video slots (the red-bordered one is the active/required slot); the bottom strip lists the camera videos.
2. For each slot, select the matching camera video from the strip (overview first, then the camera used for the plate/rear).
3. Set the clip around the violation: seek to ~3 s before the vehicle passes → **Use Current Time** under *Start Time (seconds)*; seek to ~3 s after → **Use Current Time** under *End Time (seconds)*. (FOCUS/RESTORE to seek, then click the button; the field must show the number.)
4. Check: Start < End, both within the video duration; the slot shows the chosen video.

## Step 3 - Citation Details (fill the citation)
1. Top: the 3 grabbed images must appear (no "No License Plate/Overview/Rearview Image Selected" text). If any is missing, go back to Choose Images.
2. Tabs **Citation | Registered Owner Lookup**. Vehicle Info: **License Plate*** (the plate you read), **State*** (plate state), **VIN Number***, **Description*** (e.g. colour, make, type you can see), Registration Expiration Date.
3. Owner Info: **Name*, Street Address*, City*, State*, ZIP***. Follow `self_created_data.owner_info_mode` in qa/qa.config.yaml:
   - `lookup`: use the **Registered Owner Lookup** tab and copy its result into Owner Info.
   - `test_owner`: don't open the Registered Owner Lookup tab. Fill Owner Info and VIN from `self_created_data.test_owner` (read it with `grep -n -A9 "test_owner:" qa/qa.config.yaml`), Registration Expiration Date = today + 1 year, plate/state from the video, Description from what you see (colour, make, type). Then continue to Step 4 without asking.
   - `stop`: do everything else on this step, run the required-field checks, then `note blocker "DATA: owner info not authorized - stopped before Finish Processing"` and do NOT go to Step 4.
4. Required-field checks (adhoc), BEFORE filling the final values: leave each * field empty once and confirm the app blocks Finish; invalid ZIP / VIN length; plate with lowercase or spaces; expired registration date. Then fill the correct values.

## Step 4 - Finish Processing
Only when `owner_info_mode` is `lookup` or `test_owner`, and only on an event you claimed in this run (OWNED). Click **Finish Processing** once, then verify: the event leaves Q.A. Processable Events; the event's **Citations** tab shows the citation; the dashboard **Pending Approval** count rises by 1 and the citation shows the same partner, vehicle, date/time, location and plate. Log it with `flow` and `python3 qa/ledger.py note obs "OWNED citation <id> from event <eventId>"`. Mark the feature `explored` with outcome verified.

## Adhoc checks while processing
- Compare the video overlay date/time with the event's Date & Time (same time zone). If they differ by more than a minute, `note ambiguity "overlay time <x> vs event time <y> on event <id>"` (in QA this may be reused test video - not a defect unless the team confirms).
- Grab at the very start and end of a video; grab the same frame twice; switch camera mid-selection; a video that fails to load (clear error?); plate typed differently from the grabbed frame (does the app warn?); back from Citation Details to Choose Images (are selections kept?); refresh mid-wizard.

## If LIST returns [] or seeking does nothing
The player may be custom or still loading: use its own controls (pause button, time slider, 1x speed, fullscreen) and viewport screenshots, and `note env "player not scriptable on <page>"`.
