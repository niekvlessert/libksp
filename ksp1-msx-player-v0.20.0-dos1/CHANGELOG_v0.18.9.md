# KSP1PLAY v0.18.9

## Playback track-window fix

The playback screen shows 13 track rows, while the pre-play selector shows 15.
The previous viewport calculation always used 15 rows, allowing the active track
to move outside the 13 rows actually rendered during playback.

The shared viewport calculation now scrolls when the active track reaches offset
12 and places it at offset 11. This keeps one following track visible on the
last playback row whenever one exists. The 15-row selector also benefits by
showing up to three following tracks.

No full-screen repaint was reintroduced. A viewport change redraws only the
track pane; movement inside the viewport still redraws only the affected rows
and current-title field.
