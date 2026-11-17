# Body Kaizen Sync: screen designs

Source for the iPhone app's screens (design agreed 17 Nov 2026). Each `.dc.html` file is one screen; `canvas.json`
lays them out (first run on the top row, Status, Settings and the Mac's Connections card below). They open in a
Claude design canvas, where they can be edited and clicked through. Pictures of every screen are in
[`docs/img/iphone-sync/`](../../img/iphone-sync/) and in [the design doc](../../iphone-sync.md#screens).

`StatusAway.dc.html` and `StatusMac.dc.html` reuse `Status.dc.html` with a different `state`
(`synced`, `away`, `mac`), so wording on the Status screen is changed in one place.
