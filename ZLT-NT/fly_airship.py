"""Fly the ZLT-NT airship by hand. This package ships no autopilot airframe, and
that is the point.

  python fly_airship.py            # a gamepad flies it
  python fly_airship.py --auto     # climb, hold, descend and land, unattended

PX4's airship module offers a forward thrust and two moments and nothing else: no
vectored thrust, no elevator, no ballonets -- so under it the ship can only drive
forward, which is not how an airship leaves the ground. This one has all three, its
own flight control system already drives them, and SetActuatorControls reaches them
straight.

Lift-off is vectored thrust, and the two nacelle levers must not move together. The
side pair sits 8.9 m ahead of the centre of gravity and the aft one 40.5 m behind it,
so equal vertical thrust is a nose-down moment of more than two to one: the ship
climbs with its nose swinging between +4 and -16 degrees. Split them the way LIFT
below does -- side at 0.75 of its 120 deg travel, aft at 0.36 of its 90 -- and the
moments cancel: measured pitch then stays inside one degree the whole way up.

Ballonets do not lift this model. Their valves flow with the pressure difference
across the cell, and vented at altitude for two minutes they changed the descent rate
by nothing measurable. The ship flies heavy, as the real one does, and the engines
carry it.
"""

import argparse
import sys
import time

from pterosim import PteroSim

GRPC = "localhost:10010"
AIRCRAFT = "ZLT-NT"
RATE_HZ = 50.0

# Controls.xml, in order.
DRIVE_STBD, DRIVE_PORT, DRIVE_AFT = 0, 1, 2
YAW, SIDE_SWIVEL, REAR_SWIVEL, ELEVATOR = 3, 4, 5, 6
BALLONET_FWD, BALLONET_AFT = 7, 8
CHANNELS = 9

# Straight up, and balanced: 0.75 of the side travel is 90 deg, 0.36 of the aft is 32.
# The aft one stops short on purpose -- see the moment arithmetic above.
LIFT_SIDE, LIFT_AFT = 0.75, 0.36


def clamp(v, lo=-1.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


class Airship:
    """The nine channels, and the arithmetic that keeps them sane."""

    def __init__(self, aircraft):
        self.aircraft = aircraft
        self.c = [0.0] * CHANNELS

    def set(self, throttle=None, yaw=None, elevator=None, lift=None, ballonet=None):
        if throttle is not None:
            t = clamp(throttle, 0.0, 1.0)
            self.c[DRIVE_STBD] = self.c[DRIVE_PORT] = self.c[DRIVE_AFT] = t
        if yaw is not None:
            self.c[YAW] = clamp(yaw)
        if elevator is not None:
            self.c[ELEVATOR] = clamp(elevator)
        if lift is not None:
            l = clamp(lift, 0.0, 1.0)
            self.c[SIDE_SWIVEL] = LIFT_SIDE * l
            self.c[REAR_SWIVEL] = LIFT_AFT * l
        if ballonet is not None:
            self.c[BALLONET_FWD] = self.c[BALLONET_AFT] = clamp(ballonet)

    def push(self):
        self.aircraft.set_controls(self.c)

    def rest(self):
        self.c = [0.0] * CHANNELS
        self.push()


def connect(spawn):
    sim = PteroSim(GRPC)
    found = [a for a in sim.aircraft_status() if a.aircraft_name == AIRCRAFT]
    if not found and not spawn:
        sys.exit("No %s in the scene. Spawn one, or pass --spawn." % AIRCRAFT)
    if not found:
        sim.stop()
        for a in sim.aircraft_status():
            sim.get_aircraft(a.instance_id).remove()
        sim.spawn(AIRCRAFT, x=0.0, y=0.0, z=0.0, yaw=0.0)
        time.sleep(2.0)
        found = [a for a in sim.aircraft_status() if a.aircraft_name == AIRCRAFT]

    aircraft = sim.get_aircraft(found[0].instance_id)
    # Nobody else at the controls: a connected autopilot writes the same channels at
    # 240 Hz and would win every other frame.
    try:
        aircraft.set_flight_stack("")
    except Exception as e:
        print("[note] could not take the autopilot off (%s); stop the simulation first if it fights back" % e)
    return sim, aircraft


def fly_auto(sim, ship, cruise, hold_for):
    """Climb on vectored thrust, hold, come back down, sit on the wheels."""
    t0 = time.time()
    first = list(sim.aircraft_status())[0]
    z0 = first.z / 100.0
    prev_alt, prev_t, vs = z0, time.time(), 0.0
    hover, sent = 0.65, 0.0            # hover integrates to whatever throttle holds height
    phase, mark, next_print = "climb", time.time(), 0.0
    print("climb to %.0f m, hold %.0f s, then land" % (cruise, hold_for))

    while phase != "done":
        now = time.time()
        t = now - t0
        a = list(sim.aircraft_status())[0]
        agl = a.z / 100.0 - z0
        if now - prev_t > 0.4:
            vs = (a.z / 100.0 - prev_alt) / (now - prev_t)
            prev_alt, prev_t = a.z / 100.0, now

        if phase == "climb":
            want = min(1.0, t / 3.0)
            # Spool first, swivel second: the swivel actuator takes four seconds either way.
            ship.set(throttle=want, lift=min(1.0, max(0.0, (t - 4.0) / 5.0)))
            if agl > cruise - 4.0:
                phase, mark = "hold", now
        elif phase == "land":
            want = 0.0
            ship.set(throttle=0.0, lift=1.0)
            if now - mark > 8.0:
                phase = "done"
        else:
            target = cruise if phase == "hold" else 2.0
            err = target - agl
            want = hover + 0.03 * clamp(err, -12.0, 12.0) - 0.35 * vs
            hover = clamp(hover + 0.01 * clamp(err, -6.0, 6.0) * (now - prev_t), 0.2, 0.95)
            ship.set(throttle=want, lift=1.0)
            if phase == "hold" and now - mark > hold_for:
                phase, mark = "descend", now
            elif phase == "descend" and agl < 1.2:
                phase, mark, want = "land", now, 0.0

        # No throttle slams: a step on three engines rings the hull for half a minute.
        sent += clamp(clamp(want, 0.0, 1.0) - sent, -0.02, 0.02)
        ship.set(throttle=sent)
        ship.push()

        if now > next_print:
            print("  %-8s t+%5.1fs  agl=%7.2f m  vs=%+5.2f  pitch=%6.2f  thr=%.2f"
                  % (phase, t, agl, vs, a.pitch, sent))
            next_print = now + 5.0
        time.sleep(1.0 / RATE_HZ)

    a = list(sim.aircraft_status())[0]
    print("\ndown at %.2f m, pitch %.1f deg, %.0f m from the start"
          % (a.z / 100.0 - z0, a.pitch, a.x / 100.0 - first.x / 100.0))
    ship.rest()


def fly_stick(sim, ship):
    import pygame

    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        sys.exit("No gamepad. Plug one in, or run with --auto.")
    js = pygame.joystick.Joystick(0)
    js.init()
    print("stick: %s, %d axes, %d buttons" % (js.get_name(), js.get_numaxes(), js.get_numbuttons()))
    print("""
  left stick  up/down    throttle, all three engines
  left stick  left/right yaw: rudders and the lateral thruster
  right stick up/down    elevator
  triggers               nacelles up: 0 is level flight, 1 is straight up and balanced
  button 0 / 1           vent / fill the ballonets (they trim the ship, they do not lift it)
  button 7 / Ctrl-C      stop
""")

    def axis(i, dead=0.06):
        if i >= js.get_numaxes():
            return 0.0
        v = js.get_axis(i)
        return 0.0 if abs(v) < dead else v

    t0, next_print, lift = time.time(), 0.0, 0.0
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
        if js.get_numbuttons() > 7 and js.get_button(7):
            return

        # Triggers rest at -1 on most pads, so the pair reads as one 0..1 lever.
        trig = max((axis(4) + 1.0) * 0.5, (axis(5) + 1.0) * 0.5) if js.get_numaxes() > 5 else 0.0
        lift = trig if trig > 0.0 else lift

        ballonet = 0.0
        if js.get_numbuttons() > 1:
            ballonet = -1.0 if js.get_button(0) else 1.0 if js.get_button(1) else 0.0

        ship.set(throttle=(-axis(1) + 1.0) * 0.5, yaw=axis(0), elevator=axis(3),
                 lift=lift, ballonet=ballonet)
        ship.push()

        if time.time() > next_print:
            a = list(sim.aircraft_status())[0]
            print("  t+%5.1fs  alt=%7.2f m  pitch=%6.2f  yaw=%6.1f  thr=%.2f lift=%.2f"
                  % (time.time() - t0, a.z / 100.0, a.pitch, a.yaw, ship.c[DRIVE_AFT], lift))
            next_print = time.time() + 1.0
        time.sleep(1.0 / RATE_HZ)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--auto", action="store_true", help="fly a climb-hold-land profile instead of a gamepad")
    ap.add_argument("--spawn", action="store_true", help="spawn the airship if the scene has none")
    ap.add_argument("--cruise", type=float, default=40.0, help="height above the spawn point, metres")
    ap.add_argument("--hold", type=float, default=60.0, help="seconds to hold up there")
    args = ap.parse_args()

    sim, aircraft = connect(args.spawn)
    ship = Airship(aircraft)
    # Started before a single channel is sent: the engines are sized and the command
    # buffer created by the start, and controls arriving before it have nowhere to go.
    sim.start()
    time.sleep(0.5)
    ship.rest()
    print("simulation running, %s at the controls\n" % ("the script" if args.auto else "the stick"))

    try:
        if args.auto:
            fly_auto(sim, ship, args.cruise, args.hold)
        else:
            fly_stick(sim, ship)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        ship.rest()


if __name__ == "__main__":
    main()
