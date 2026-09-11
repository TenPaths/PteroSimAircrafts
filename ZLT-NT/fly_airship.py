"""Fly the ZLT-NT airship by hand, or let it fly a profile on its own.

  python fly_airship.py                 # keyboard, gamepad, or both
  python fly_airship.py --auto          # climbs, holds, descends and lands

Spawn the airship in the editor first; this script only flies what is already there.

  command                              key           gamepad
  throttle, all three engines          W / S         left stick Y
  throttle - cut                       Space
  yaw: rudders and lateral thruster    A / D         left stick X
  elevator: nose up / down             Up / Down     right stick Y
  nacelles up / down                   Q / E         triggers
  ballonets - vent / fill              Z / X         buttons 0 / 1
  stop                                 Esc           button 7

Throttle and nacelles are levers and hold where they are left; yaw and elevator spring
back. See README.md for what the ship does with all this.
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

# Straight up, and balanced: 0.75 of the side travel is 90 deg, 0.36 of the aft is 32. The
# aft one stops short on purpose -- equal thrust would be a two-to-one nose-down moment.
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


def connect():
    sim = PteroSim(GRPC)
    found = [a for a in sim.aircraft_status() if a.aircraft_name == AIRCRAFT]
    if not found:
        sys.exit("No %s in the scene -- spawn one in the editor first." % AIRCRAFT)

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


KEYS = [
    ("W / S", "throttle up / down, all three engines"),
    ("Space", "throttle to zero"),
    ("A / D", "yaw left / right: rudders and the lateral thruster"),
    ("Up / Down", "elevator: nose up / down"),
    ("Q / E", "nacelles up / down -- Q to the balanced lift setting, E back to level"),
    ("Z / X", "ballonets: vent / fill (they trim the ship, they do not lift it)"),
    ("Esc", "stop"),
]

PAD = [
    ("left stick up/down", "throttle"),
    ("left stick left/right", "yaw"),
    ("right stick up/down", "elevator"),
    ("triggers", "nacelles: 0 is level flight, 1 is straight up and balanced"),
    ("button 0 / 1", "vent / fill the ballonets"),
    ("button 7", "stop"),
]


def fly_manual(sim, ship):
    """Keyboard, gamepad, or both at once -- whichever moves wins each channel.

    The window is where the keyboard focus lives; it also shows the levers and the ship.
    """
    import pygame

    pygame.init()
    pygame.joystick.init()
    js = None
    if pygame.joystick.get_count():
        js = pygame.joystick.Joystick(0)
        js.init()
        print("stick: %s, %d axes, %d buttons" % (js.get_name(), js.get_numaxes(), js.get_numbuttons()))
    print()
    print("keyboard (click the window first):")
    for key, what in KEYS:
        print("    %-10s %s" % (key, what))
    if js:
        print()
        print("gamepad:")
        for key, what in PAD:
            print("    %-22s %s" % (key, what))
    print()

    screen = pygame.display.set_mode((620, 300))
    pygame.display.set_caption("ZLT-NT -- click here, then fly")
    font = pygame.font.SysFont("consolas", 15)
    big = pygame.font.SysFont("consolas", 17, bold=True)

    def axis(i, dead=0.06):
        if not js or i >= js.get_numaxes():
            return 0.0
        v = js.get_axis(i)
        return 0.0 if abs(v) < dead else v

    def held(keys, *names):
        return any(keys[getattr(pygame, "K_" + n)] for n in names)

    def triggers():
        return max((axis(4) + 1.0) * 0.5, (axis(5) + 1.0) * 0.5) if js and js.get_numaxes() > 5 else 0.0

    # Where the triggers rest, read once: a DualSense parks axes 4 and 5 at +1, and taken as a
    # lever position that put the nacelles straight up before anyone had touched anything.
    trig_rest = triggers()
    t0, next_print, throttle, lift = time.time(), 0.0, 0.0, 0.0
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return
        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE] or (js and js.get_numbuttons() > 7 and js.get_button(7)):
            return

        step = 1.0 / RATE_HZ
        throttle += (held(keys, "w") - held(keys, "s")) * 0.5 * step
        lift += (held(keys, "q") - held(keys, "e")) * 0.4 * step
        if keys[pygame.K_SPACE]:
            throttle = 0.0
        # The pad wins a channel it is actually moving, so both can be held at once.
        trig = triggers()
        if abs(trig - trig_rest) > 0.05:
            lift = trig
        if abs(axis(1)) > 0.0:
            throttle = (-axis(1) + 1.0) * 0.5
        throttle, lift = clamp(throttle, 0.0, 1.0), clamp(lift, 0.0, 1.0)

        yaw = clamp(held(keys, "d", "RIGHT") - held(keys, "a", "LEFT") + axis(0))
        elevator = clamp(held(keys, "DOWN") - held(keys, "UP") + axis(3))
        ballonet = clamp(held(keys, "x") - held(keys, "z")
                         + (js and js.get_numbuttons() > 1 and (js.get_button(1) - js.get_button(0)) or 0))

        ship.set(throttle=throttle, yaw=yaw, elevator=elevator, lift=lift, ballonet=ballonet)
        ship.push()

        a = list(sim.aircraft_status())[0]
        screen.fill((22, 26, 32))
        screen.blit(big.render("throttle %.2f   nacelles %.2f   yaw %+.1f   elevator %+.1f"
                               % (throttle, lift, yaw, elevator), True, (235, 235, 230)), (14, 12))
        screen.blit(big.render("alt %6.1f m   pitch %+6.1f   heading %5.1f"
                               % (a.z / 100.0, a.pitch, a.yaw), True, (150, 200, 255)), (14, 36))
        for i, (key, what) in enumerate(KEYS):
            screen.blit(font.render("%-10s %s" % (key, what), True, (170, 175, 180)), (14, 78 + i * 22))
        pygame.display.flip()

        if time.time() > next_print:
            print("  t+%5.1fs  alt=%7.2f m  pitch=%6.2f  yaw=%6.1f  thr=%.2f lift=%.2f"
                  % (time.time() - t0, a.z / 100.0, a.pitch, a.yaw, throttle, lift))
            next_print = time.time() + 1.0
        time.sleep(step)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--auto", action="store_true", help="fly a climb-hold-land profile instead of flying it yourself")
    ap.add_argument("--cruise", type=float, default=40.0, help="height above the spawn point, metres")
    ap.add_argument("--hold", type=float, default=60.0, help="seconds to hold up there")
    args = ap.parse_args()

    sim, aircraft = connect()
    ship = Airship(aircraft)
    # Started before a single channel is sent: the engines are sized and the command
    # buffer created by the start, and controls arriving before it have nowhere to go.
    sim.start()
    time.sleep(0.5)
    ship.rest()
    print("simulation running, %s at the controls\n" % ("the script" if args.auto else "you"))

    try:
        if args.auto:
            fly_auto(sim, ship, args.cruise, args.hold)
        else:
            fly_manual(sim, ship)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        ship.rest()


if __name__ == "__main__":
    main()
