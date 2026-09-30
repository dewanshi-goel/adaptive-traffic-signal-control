import os

HERE = os.path.dirname(os.path.abspath(__file__))
SCEN_DIR = os.path.join(HERE, "..", "sumo", "scenarios")

# where a vehicle entering on each approach goes for each turn
TURNS = {
    "left0A0":   {"straight": "A0right0",  "left": "A0top0",    "right": "A0bottom0"},
    "right0A0":  {"straight": "A0left0",   "left": "A0bottom0", "right": "A0top0"},
    "top0A0":    {"straight": "A0bottom0", "left": "A0right0",  "right": "A0left0"},
    "bottom0A0": {"straight": "A0top0",    "left": "A0left0",   "right": "A0right0"},
}
SPLIT = {"straight": 0.72, "left": 0.12, "right": 0.16}


def demand(ew, ns):
    """vehicles per hour on each approach"""
    return {"left0A0": ew, "right0A0": ew, "top0A0": ns, "bottom0A0": ns}


SCENARIOS = {
    "light_balanced":   demand(ew=200, ns=200),
    "lopsided":         demand(ew=490, ns=190),
    "heavy_balanced":   demand(ew=650, ns=650),
    "extreme_lopsided": demand(ew=700, ns=100),
}


def write_all():
    os.makedirs(SCEN_DIR, exist_ok=True)
    paths = {}
    for name, volumes in SCENARIOS.items():
        path = os.path.abspath(os.path.join(SCEN_DIR, f"{name}.rou.xml"))
        lines = ["<routes>",
                 '    <vType id="car" vClass="passenger" length="5" accel="2.6" '
                 'decel="4.5" sigma="0.5" maxSpeed="13.89"/>']
        for edge, vph in volumes.items():
            for turn, share in SPLIT.items():
                p = vph * share / 3600.0
                lines.append(
                    f'    <flow id="{edge}_{turn}" type="car" from="{edge}" '
                    f'to="{TURNS[edge][turn]}" begin="0" end="3600" '
                    f'probability="{p:.5f}" departLane="best" departSpeed="max"/>')
        lines.append("</routes>")
        with open(path, "w") as f:
            f.write("\n".join(lines))
        paths[name] = path
    return paths


def add_emergency(route_path, rate_per_hour=4.5):
    """Appends emergency-vehicle flows (one per approach) to an existing route file."""
    per_edge = rate_per_hour / 4 / 3600.0  # probability per second, per approach
    lines = [
        '    <vType id="emergency" vClass="emergency" length="6" accel="3.0" '
        'decel="5.0" sigma="0.2" maxSpeed="20.0" guiShape="emergency" color="1,0,0"/>'
    ]
    for edge, turns in TURNS.items():
        dest = turns["straight"]
        lines.append(
            f'    <flow id="EMG_{edge}" type="emergency" from="{edge}" to="{dest}" '
            f'begin="0" end="3600" probability="{per_edge:.6f}" '
            f'departLane="best" departSpeed="max"/>')

    with open(route_path, "r") as f:
        content = f.read()
    content = content.replace("</routes>", "\n".join(lines) + "\n</routes>")
    with open(route_path, "w") as f:
        f.write(content)