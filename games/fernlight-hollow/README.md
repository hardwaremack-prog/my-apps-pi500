# Fernlight Hollow

A low-poly nature valley made for the **Raspberry Pi 500** (8 GB). It's one HTML file that runs offline in Chromium with no install.

![The valley](screenshots/valley.jpg)

## What's in the valley

- A winding river and lake, pine and leafy forests, swaying grass and wildflower meadows
- A full day and night cycle with sun, moon, stars, clouds and birds
- A campfire with rising embers, and fireflies along the riverbanks after dark
- Deer herds, rabbits, ducks on the lake, and fish that jump out of the river. Get too close and the animals run.
- **The Blackwood:** a patch of dead forest where the Rootwalker hunts anyone who lingers. Hold Shift to sprint out before it reaches you.
- Ambient sound: wind, birdsong, crickets and the crackling fire, all generated in the browser with no audio files

| | |
|---|---|
| ![Deer in the meadow](screenshots/deer.jpg) | ![Campfire at night](screenshots/campfire.jpg) |
| ![The Blackwood from above](screenshots/blackwood.jpg) | ![Inside the Blackwood](screenshots/rootwalker.jpg) |

## Run it

1. Copy `index.html` to the Pi.
2. Double-click it, or open it in Chromium.

For the best frame rate, make sure hardware acceleration is on in Chromium.

## Controls

| Key | Action |
|---|---|
| Drag mouse | Look around |
| W A S D | Move |
| Shift | Move faster / sprint |
| Space / C | Fly up / down |
| G | Walk on the ground or fly |
| R | Jump to the campfire |
| T | Speed up time |
| 1 2 3 | Low, medium, high detail |
| H | Hide the overlay |
| P | Save a screenshot |
| F | Fullscreen |

## Tuned for the Pi

- It detects the Pi's VideoCore GPU and starts on Medium detail.
- If the frame rate drops, it lowers the render resolution by itself. The on-screen stats show FPS, resolution, triangles and draw calls.
- Trees and grass outside the view or past the fog aren't drawn, and lighting is per-vertex to keep the GPU load low.

Built with [three.js](https://threejs.org) r128, which is bundled into the file.

See also **[Fernlight Frostfall](https://github.com/hardwaremack-prog/fernlight-frostfall)**, the survival version, initially designed for an overclocked RPi 500.
