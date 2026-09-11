# ZLT-NT

A Zeppelin NT airship for PteroSim: JSBSim flight model by Anders Gidenstam (GPL-2.0-or-later,
see LICENSE and NOTICE), fitted here with visuals, a livery and a script to fly it by hand.

## Flying it

The package ships no autopilot airframe, and that is the point: PX4's airship module offers a
forward thrust and two moments, and an airship leaves the ground by vectoring its engines --
which no autopilot output maps to. `fly_airship.py` drives the nine channels directly.

```
python fly_airship.py --auto --spawn      # climb to 40 m, hold, descend and land, unattended
python fly_airship.py                     # a gamepad flies it
```

Spawn the airship in the editor first, or pass `--spawn` to have the script do it. `--cruise`
and `--hold` set the height in metres and how long to hold there. The script needs the
`pterosim` SDK on the path, and `pygame` as well if you fly with a gamepad.

With a gamepad:

| control | does |
| --- | --- |
| left stick, up/down | throttle, all three engines |
| left stick, left/right | yaw: rudders and the lateral thruster |
| right stick, up/down | elevator |
| triggers | nacelles: 0 is level flight, 1 is straight up and balanced |
| buttons 0 / 1 | vent / fill the ballonets |
| button 7 or Ctrl-C | stop |

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
