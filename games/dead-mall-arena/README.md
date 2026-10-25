# Dead Mall Arena — LAN Edition

A remake of Dead Mall Arena with modern graphics and real local-network multiplayer.
The whole two-floor mall is still here — the arcade, the dive bar, the pizza conveyor,
the fortune teller, the kart museum, Big Vinny and the ex-employee upstairs — now with:

- **New lighting and surfaces:** worn 80s floor tile with standing water, water-stained drop
  ceilings, painted block walls, a terrazzo mezzanine with brass strips, sun shining through
  the skylight and casting the grid's shadow, soft sunbeams, drifting dust, glowing neon,
  ambient occlusion, reflections and film grain (on Ultra).
- **LAN multiplayer:** one computer runs a tiny server, everyone else on your Wi-Fi or
  network opens its address. Everyone shares the same aliens and the same power-ups,
  updated 20 times a second. No internet or account needed.
- **One game, every machine:** each player picks their own graphics level, so the
  AMD 395 on Ultra and a Pi 500 on the Pi setting can play in the same mall.

## Start playing

**This folder is set up for: the Raspberry Pi 500 / Pi 5 (Pi graphics). Double-click start-pi.sh and choose Execute. A terminal window opens with the server and the game opens in Chromium. Close that window when you are done.**

You need Python 3 (already on Raspberry Pi OS; on Windows get it from python.org and tick
"Add python.exe to PATH" while installing).

| You want to... | Do this |
|---|---|
| Host a game | Run `start-pi.sh`. It starts the server and opens the game. |
| Join a friend's game | Open the address their server window shows, like `http://192.168.1.20:8090`, in Chrome / Chromium. Or run `./join-game.sh 192.168.1.20`. |
| Play solo | Same as hosting: run `start-pi.sh` and just play. The aliens are still there. |

The server window lists the address friends should open. Leave it open while you play.
It starts on port 8090. If something else is already using that port, it tries 8091,
then 8092 and so on, and the address it shows always has the right port in it.
The first player in the mall becomes the **host**: their browser runs the alien squad
and power-ups for everyone. If they leave (or switch away from the game), the next player
takes over automatically.

**If the game won't start:** it shows the reason on screen (for example, 3D graphics turned off in
the browser) instead of hanging on the loading screen. On a Pi, Chromium needs
*Use graphics acceleration when available* switched on in its settings.

**Windows firewall:** the first time, Windows may ask whether Python can use the network.
Allow it on **Private networks**, or other computers can't join.

## Graphics settings

Pick on the start screen. Auto-detect chooses for you.

| Setting | Made for | What you get |
|---|---|---|
| Ultra (AMD 395) | Radeon 8060S / any strong GPU | Sun shadows through the skylight, shadowed fluorescent lights, ambient occlusion, reflections, bloom, 4x anti-aliasing, film grain |
| High | Gaming laptops and desktops | Ultra with smaller shadows and lighter AO |
| Medium | Older or integrated graphics | Sun shadows, bloom and reflections, no AO |
| Pi 500 | Raspberry Pi 5 / 500 | Faster lighting, nearest 6 lights only, 80% resolution, no post effects, the still parts of the mall merged into big batches |

If a machine can't keep up, the game quietly lowers its resolution a step at a time
and raises it again when it can. Press **F** in game to see your frame rate.

## Controls

| Key | Action |
|---|---|
| WASD / Mouse | Move and look |
| Hold click | Fire |
| R | Reload the shotgun |
| E | Interact (bar, jukebox, pool, darts, fortune teller, vending machines, grenade stand) |
| G | Throw a grenade |
| Y / N | Answer yes or no |
| T | Text chat |
| M | Toggle music |
| F | Show frame rate |
| Esc | Release the mouse |

## Files

- `server.py` — the LAN server (Python standard library only)
- `public/` — the game. three.js and the fonts are bundled, so it works with no internet.
- `public/config.js` — default graphics level for this package

Made by hardwaremack.
