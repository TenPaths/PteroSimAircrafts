# ZLT-NT

A Zeppelin NT airship for PteroSim: JSBSim flight model by Anders Gidenstam (GPL-2.0-or-later,
see LICENSE and NOTICE), fitted here with visuals, a livery and a script to fly it by hand.

## Flying it

The package ships no autopilot airframe, and that is the point: PX4's airship module offers a
forward thrust and two moments, and an airship leaves the ground by vectoring its engines --
which no autopilot output maps to. `fly_airship.py` drives the nine channels directly.

```
python fly_airship.py --auto --spawn      # climb to 40 m, hold, descend and land, unattended
python fly_airship.py                     # you fly it: keyboard, gamepad, or both
```

Spawn the airship in the editor first, or pass `--spawn` to have the script do it. `--cruise`
and `--hold` set the height in metres and how long to hold there. The script needs the
`pterosim` SDK on the path, and `pygame` for flying it yourself.

Without `--auto` a small window opens: click it, because that is where the keyboard focus
lives, and it shows the levers and the ship's state while you fly. A gamepad, if one is
plugged in, works at the same time -- each channel takes whichever of the two is moving.

The throttle and the nacelles are levers: they stay where you leave them. The rudder and the
elevator spring back to centre, as a stick does.

### Keyboard

| key | does |
| --- | --- |
| `W` / `S` | throttle up / down, all three engines |
| `Space` | throttle to zero |
| `A` / `D` | yaw left / right: rudders and the lateral thruster |
| `Up` / `Down` | elevator: nose up / down |
| `Q` / `E` | nacelles up / down -- `Q` to the balanced lift setting, `E` back to level |
| `Z` / `X` | ballonets: vent / fill |
| `Esc` | stop |

### Gamepad

| control | does |
| --- | --- |
| left stick, up/down | throttle |
| left stick, left/right | yaw |
| right stick, up/down | elevator |
| triggers | nacelles: released is level flight, pulled is straight up and balanced |
| buttons 0 / 1 | vent / fill the ballonets |
| button 7 | stop |

### Taking off by hand

Open the throttle with `W` and let the engines spool for three or four seconds, then hold `Q`
until the nacelles read 1.00 -- the swivel actuator takes about four seconds for full travel.
The ship climbs at 0.7 m/s with the nose within a degree of level. To come down, `E` back to
level flight and ease the throttle off; to land, cut it with `Space` and let it settle on its
wheels, which it does at four degrees nose-up.

## Two things worth knowing before you fly

**The nacelle levers must not move together.** The side pair sits 8.9 m ahead of the centre of
gravity and the aft one 40.5 m behind it, so equal vertical thrust is a nose-down moment of
more than two to one: with both at 90 degrees the ship climbs with its nose swinging between
+4 and -16 degrees. The script's single lift lever splits them -- side at 0.75 of its 120
degree travel, aft at 0.36 of its 90 -- and the moments cancel. Measured over a 70 second
climb:

| side / aft | climb | mean pitch | pitch range |
| --- | --- | --- | --- |
| 0.75 / 1.00 | 20.8 m | -9.5 deg | 13.9 deg |
| 0.75 / 0.36 | 34.3 m | +0.5 deg | 1.9 deg |

**Ballonets do not lift this model.** Their valves flow with the pressure difference across the
cell, and vented at altitude for two minutes they changed the descent rate by nothing
measurable. The ship flies heavy, as the real one does, and the engines carry it.

## What is in here

`ZLT-NT.xml` and `Systems/` are the flight model; `Controls.xml` maps the nine channels onto
it; `Visual.xml` hangs the meshes and names what moves each one -- three fins of the
inverted-Y tail, the two side pods and the tail spinner, each hinged where the ship hinges it.
`meshes/` and `textures/` are built from the source hull by `Scripts/zlt_nt/cut_hull.py` and
`livery.py` in the simulator's own repository, not from this package; re-run them only when the
source model changes.
