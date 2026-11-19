# AlertBus event processing: watching videos and processing an event like a human reviewer

Page: `qa-alertbus-processing.aws.buspatrol.com/process/<eventId>` (Event Processing > Q.A. Processable Events > open event).
Header row: Date & Time | Vehicle | Partner | Location | Violations | Reviewer. Wizard tabs: **Choose Images → Choose Videos → Citation Details → Finish Processing**.

Viewing a frame = `browser_take_screenshot` WITHOUT `filename` (the image is shown to you). Save evidence only WITH `filename`.
Budget: at most 25 viewing screenshots per event. Never write a full plate, owner name or address into notes, defects or the model.

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

## Step 1 - Choose Images (find the violation and grab 3 images)
1. The left grid shows camera tiles (e.g. overview, overview, windshield, inner lane, outer lane). Tiles showing "Failed to load video" or labelled "missing" can't be used; note them once with `note obs`. A tile marked "Selected" is the one loaded in the main player.
2. Click a usable **overview** tile so it plays in the main player. Run LIST and pick the MAIN player (largest w×h).
3. Coarse scan: FOCUS the main player at 6 evenly spaced times across its duration and view each frame. Look for the bus's **red STOP sign / stop arm extended** (red sign at the frame's left edge) and a **vehicle passing the bus** while it's out. Use the burned-in overlay (channel, date/time, GPS) to keep track.
4. Refine around that moment in 0.5 s, then 0.2 s steps:
   - **Overview frame**: the stop arm is clearly extended AND the vehicle is beside or passing the bus (proves the violation).
   - **License-plate frame**: the vehicle's plate is largest and sharpest (often a second or two later, or on another camera such as windshield/rear).
   - **Rearview frame**: the vehicle seen from behind after passing (rear plate / rear camera if available).
5. For each: FOCUS to that time → view it → RESTORE → click the right-side button **Grab Overview**, **Grab License Plate** or **Grab Rearview**. Switch camera tiles as needed (the grab uses the video currently in the main player).
6. Read the plate characters and state. Accept only if every character is clearly legible in at least two frames; otherwise don't guess: `note ambiguity "plate not legible, event <id>"` and use the disapproval path if the app offers one.

## Step 2 - Choose Videos (attach the evidence clips)
1. The top shows 3 video slots (the red-bordered one is the active/required slot); the bottom strip lists the camera videos.
2. For each slot, select the matching camera video from the strip (overview first, then the camera used for the plate/rear).
3. Set the clip around the violation: play/seek to ~3 s before the vehicle passes → **Use Current Time** under *Start Time (seconds)*; seek to ~3 s after → **Use Current Time** under *End Time (seconds)*. (FOCUS/RESTORE to seek, then click the button; the field must show the number.)
4. Check: Start < End, both within the video duration; the slot shows the chosen video.

## Step 3 - Citation Details (fill the citation)
1. Top: the 3 grabbed images must appear (no "No License Plate/Overview/Rearview Image Selected" text). If any is missing, go back to Choose Images.
2. Tabs **Citation | Registered Owner Lookup**. Vehicle Info: **License Plate*** (the plate you read), **State*** (plate state), **VIN Number***, **Description*** (e.g. colour, make, type you can see), Registration Expiration Date.
3. Owner Info: **Name*, Street Address*, City*, State*, ZIP***. Use the **Registered Owner Lookup** tab result ONLY if `self_created_data` allows it and lookups in QA are confirmed not to reach real DMV records; otherwise stop here and `note blocker "DATA: owner lookup not authorized"`.
4. Required-field checks (adhoc): leave each * field empty once and confirm the app blocks Finish; invalid ZIP / VIN length; plate with lowercase or spaces; expired registration date.

## Step 4 - Finish Processing
Only on an event you claimed in this run (OWNED). Submit once, then verify: the event leaves Q.A. Processable Events; the event's **Citations** tab shows the citation; the dashboard **Pending Approval** count rises by 1 and the citation shows the same partner, vehicle, date/time, location and plate. Log it with `flow` and `note obs "OWNED citation <id> from event <eventId>"`.

## If LIST returns [] or seeking does nothing
The player may be custom or still loading: use its own controls (pause button, time slider, 1x speed, fullscreen) and viewport screenshots, and `note env "player not scriptable on <page>"`.
