"""
parser.py - Robust NS2 .nam trace file parser.

Extracts nodes, links, packet events (+, -, r, d), queues, and colors.
Reconstructs packet flights (departure to arrival/drop intervals) for real-time animation.
Includes automatic topology layout fallback if coordinates are missing.
"""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class Node:
    id: int
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    shape: str = "circle"
    color: str = "black"
    label: str = ""
    has_explicit_pos: bool = False


@dataclass
class Link:
    src: int
    dst: int
    bandwidth: float = 1e6    # bits per second
    delay: float = 0.01       # seconds
    status: str = "UP"
    color: str = "#808080"
    orientation: str = ""


@dataclass
class PacketEvent:
    event_type: str           # '+', '-', 'r', 'd'
    time: float
    src: int
    dst: int
    pkt_type: str = "cbr"
    size: int = 1000
    color_id: str = "0"
    pkt_id: int = 0
    flow_id: int = 0
    raw_params: Dict[str, str] = field(default_factory=dict)


@dataclass
class PacketFlight:
    """Represents a packet traveling along a link during [t_start, t_end]."""
    pkt_id: int
    flow_id: int
    src: int
    dst: int
    pkt_type: str
    size: int
    color_id: str
    t_start: float
    t_end: float
    was_dropped: bool = False
    drop_time: Optional[float] = None


@dataclass
class DropEvent:
    time: float
    src: int
    dst: int
    pkt_id: int
    pkt_type: str
    color_id: str
    x: float
    y: float


@dataclass
class NamData:
    nodes: Dict[int, Node] = field(default_factory=dict)
    links: Dict[Tuple[int, int], Link] = field(default_factory=dict)
    color_table: Dict[str, str] = field(default_factory=dict)
    events: List[PacketEvent] = field(default_factory=list)
    flights: List[PacketFlight] = field(default_factory=list)
    drops: List[DropEvent] = field(default_factory=list)
    min_time: float = 0.0
    max_time: float = 0.0
    total_packets: int = 0
    total_drops: int = 0


def parse_nam_line(line: str) -> Tuple[Optional[str], Dict[str, str]]:
    """
    Parses a single line of a .nam file.
    Returns (action_type, dictionary_of_parameters).
    """
    line = line.strip()
    if not line or line.startswith('#'):
        return None, {}

    tokens = line.split()
    if not tokens:
        return None, {}

    action = tokens[0]
    params: Dict[str, str] = {}

    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token.startswith('-') and len(token) > 1:
            flag = token[1:]
            # Check if next token exists and is a value (not another flag)
            if i + 1 < len(tokens) and not (tokens[i + 1].startswith('-') and len(tokens[i + 1]) > 1):
                params[flag] = tokens[i + 1]
                i += 2
            else:
                params[flag] = "true"
                i += 1
        else:
            i += 1

    return action, params


def parse_bandwidth(bw_str: str) -> float:
    """Parse bandwidth string like 1Mb, 100Kb, 1000000 into bits/sec."""
    bw_str = bw_str.strip().lower()
    if bw_str.endswith('mb'):
        return float(bw_str[:-2]) * 1e6
    elif bw_str.endswith('kb'):
        return float(bw_str[:-2]) * 1e3
    elif bw_str.endswith('gb'):
        return float(bw_str[:-2]) * 1e9
    elif bw_str.endswith('b'):
        return float(bw_str[:-1])
    try:
        return float(bw_str)
    except ValueError:
        return 1e6


def parse_delay(delay_str: str) -> float:
    """Parse delay string like 10ms, 1s, 0.01 into seconds."""
    delay_str = delay_str.strip().lower()
    if delay_str.endswith('ms'):
        return float(delay_str[:-2]) * 1e-3
    elif delay_str.endswith('us'):
        return float(delay_str[:-2]) * 1e-6
    elif delay_str.endswith('s'):
        return float(delay_str[:-1])
    try:
        return float(delay_str)
    except ValueError:
        return 0.01


def compute_auto_layout(nodes: Dict[int, Node], links: Dict[Tuple[int, int], Link]) -> None:
    """
    Applies a force-directed spring layout if nodes do not have distinct coordinates.
    Positions nodes nicely in a bounding box centered around (400, 300).
    """
    if not nodes:
        return

    # Check if we already have non-zero distinct coordinates
    positions = {(n.x, n.y) for n in nodes.values()}
    all_zero_or_identical = (len(positions) <= 1)

    if not all_zero_or_identical:
        # Check if they have explicit positions
        if all(n.has_explicit_pos for n in nodes.values()):
            return

    node_ids = sorted(nodes.keys())
    n_count = len(node_ids)

    # Initial circular layout
    radius = min(300.0, max(120.0, n_count * 45.0))
    center_x, center_y = 450.0, 350.0

    pos: Dict[int, Tuple[float, float]] = {}
    for idx, nid in enumerate(node_ids):
        angle = 2.0 * math.pi * idx / n_count
        pos[nid] = (
            center_x + radius * math.cos(angle),
            center_y + radius * math.sin(angle)
        )

    # Simplified spring-embedder simulation
    iterations = 60
    k_repel = 40000.0
    k_attract = 0.05
    damping = 0.85

    vel = {nid: [0.0, 0.0] for nid in node_ids}

    # Extract unique undirected link pairs
    connected_pairs = set()
    for (src, dst) in links.keys():
        if src in nodes and dst in nodes and src != dst:
            connected_pairs.add(tuple(sorted([src, dst])))

    for _ in range(iterations):
        # Repulsion between all node pairs
        for i in range(n_count):
            id_i = node_ids[i]
            px_i, py_i = pos[id_i]
            for j in range(i + 1, n_count):
                id_j = node_ids[j]
                px_j, py_j = pos[id_j]
                dx = px_i - px_j
                dy = py_i - py_j
                dist_sq = dx * dx + dy * dy
                dist = math.sqrt(dist_sq) if dist_sq > 0.001 else 0.01
                force = k_repel / max(dist_sq, 400.0)
                fx = (dx / dist) * force
                fy = (dy / dist) * force
                vel[id_i][0] += fx
                vel[id_i][1] += fy
                vel[id_j][0] -= fx
                vel[id_j][1] -= fy

        # Attraction along links
        for (src, dst) in connected_pairs:
            px_s, py_s = pos[src]
            px_d, py_d = pos[dst]
            dx = px_d - px_s
            dy = py_d - py_s
            dist = math.sqrt(dx * dx + dy * dy)
            fx = dx * k_attract
            fy = dy * k_attract
            vel[src][0] += fx
            vel[src][1] += fy
            vel[dst][0] -= fx
            vel[dst][1] -= fy

        # Apply displacement
        for nid in node_ids:
            vx = max(-30.0, min(30.0, vel[nid][0]))
            vy = max(-30.0, min(30.0, vel[nid][1]))
            px, py = pos[nid]
            pos[nid] = (px + vx, py + vy)
            vel[nid][0] *= damping
            vel[nid][1] *= damping

    # Assign positions back to nodes
    for nid in node_ids:
        nodes[nid].x = round(pos[nid][0], 2)
        nodes[nid].y = round(pos[nid][1], 2)


def parse_nam_file(filepath: str) -> NamData:
    """
    Parses an NS2 .nam file and returns structured NamData.
    """
    data = NamData()
    default_colors = {
        "0": "#3498DB",   # Blue
        "1": "#E74C3C",   # Red
        "2": "#2ECC71",   # Green
        "3": "#F39C12",   # Orange
        "4": "#9B59B6",   # Purple
        "5": "#1ABC9C",   # Turquoise
        "6": "#E67E22",   # Carrot
        "cbr": "#3498DB",
        "tcp": "#E74C3C",
        "ack": "#2ECC71",
        "udp": "#9B59B6",
    }
    data.color_table.update(default_colors)

    raw_lines: List[Tuple[str, Dict[str, str]]] = []

    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            action, params = parse_nam_line(line)
            if action:
                raw_lines.append((action, params))

    # Phase 1: Parse entities (nodes, links, colors)
    for action, params in raw_lines:
        if action == 'c':  # Color definition: c -t * -i 1 -n red
            cid = params.get('i', '')
            cname = params.get('n', '')
            if cid and cname:
                data.color_table[cid] = cname

        elif action == 'n':  # Node: n -t * -s 0 -x 50 -y 50 -v circle -c black
            nid_str = params.get('s')
            if nid_str is None:
                continue
            try:
                nid = int(nid_str)
            except ValueError:
                continue

            node = data.nodes.get(nid, Node(id=nid))
            if 'x' in params and 'y' in params:
                try:
                    node.x = float(params['x'])
                    node.y = float(params['y'])
                    node.has_explicit_pos = True
                except ValueError:
                    pass
            if 'Z' in params:
                try:
                    node.z = float(params['Z'])
                except ValueError:
                    pass
            if 'v' in params:
                node.shape = params['v']
            if 'c' in params:
                node.color = params['c']
            if 'l' in params:
                node.label = params['l']
            else:
                if not node.label:
                    node.label = f"n{nid}"

            data.nodes[nid] = node

        elif action == 'l':  # Link: l -t * -s 0 -d 1 -S UP -r 1000000 -D 0.01
            src_str = params.get('s')
            dst_str = params.get('d')
            if src_str is None or dst_str is None:
                continue
            try:
                src = int(src_str)
                dst = int(dst_str)
            except ValueError:
                continue

            # Ensure nodes exist
            if src not in data.nodes:
                data.nodes[src] = Node(id=src, label=f"n{src}")
            if dst not in data.nodes:
                data.nodes[dst] = Node(id=dst, label=f"n{dst}")

            bw = parse_bandwidth(params.get('r', '1Mb'))
            delay = parse_delay(params.get('D', '0.01'))
            status = params.get('S', 'UP')
            color = params.get('c', '#808080')
            orientation = params.get('o', '')

            link = Link(src=src, dst=dst, bandwidth=bw, delay=delay, status=status, color=color, orientation=orientation)
            data.links[(src, dst)] = link

    # Check and perform auto-layout if needed
    compute_auto_layout(data.nodes, data.links)

    # Phase 2: Parse packet events
    # Packet events: +, -, r, d
    active_in_flight: Dict[Tuple[int, int, int], List[PacketEvent]] = {}
    # Key: (pkt_id, src, dst) -> list of dequeue events waiting for receive/drop

    min_t = float('inf')
    max_t = 0.0

    for action, params in raw_lines:
        if action not in ('+', '-', 'r', 'd'):
            continue

        t_str = params.get('t', '0')
        if t_str == '*':
            continue
        try:
            time_val = float(t_str)
        except ValueError:
            continue

        try:
            src = int(params.get('s', '0'))
            dst = int(params.get('d', '0'))
        except ValueError:
            continue

        pkt_id = int(params.get('i', '0'))
        flow_id = int(params.get('a', '0'))
        pkt_type = params.get('p', 'cbr').lower()
        size = int(params.get('e', '1000'))
        color_id = params.get('c', '0')

        event = PacketEvent(
            event_type=action,
            time=time_val,
            src=src,
            dst=dst,
            pkt_type=pkt_type,
            size=size,
            color_id=color_id,
            pkt_id=pkt_id,
            flow_id=flow_id,
            raw_params=params
        )
        data.events.append(event)

        if time_val < min_t:
            min_t = time_val
        if time_val > max_t:
            max_t = time_val

        # Pair dequeue (-) with receive (r) or drop (d)
        flight_key = (pkt_id, src, dst)

        if action == '-':
            # Dequeued, starts traveling over link
            if flight_key not in active_in_flight:
                active_in_flight[flight_key] = []
            active_in_flight[flight_key].append(event)

        elif action == 'r':
            # Packet received at destination
            if flight_key in active_in_flight and active_in_flight[flight_key]:
                deq_event = active_in_flight[flight_key].pop(0)
                flight = PacketFlight(
                    pkt_id=pkt_id,
                    flow_id=flow_id,
                    src=src,
                    dst=dst,
                    pkt_type=pkt_type,
                    size=size,
                    color_id=color_id,
                    t_start=deq_event.time,
                    t_end=max(time_val, deq_event.time + 1e-5),
                    was_dropped=False
                )
                data.flights.append(flight)
            else:
                # If no matching dequeue (e.g. initial packet), estimate arrival using link delay
                link = data.links.get((src, dst))
                est_delay = link.delay if link else 0.01
                flight = PacketFlight(
                    pkt_id=pkt_id,
                    flow_id=flow_id,
                    src=src,
                    dst=dst,
                    pkt_type=pkt_type,
                    size=size,
                    color_id=color_id,
                    t_start=max(0.0, time_val - est_delay),
                    t_end=time_val,
                    was_dropped=False
                )
                data.flights.append(flight)

        elif action == 'd':
            # Packet dropped
            data.total_drops += 1
            node_src = data.nodes.get(src)
            drop_x = node_src.x if node_src else 0.0
            drop_y = node_src.y if node_src else 0.0

            if flight_key in active_in_flight and active_in_flight[flight_key]:
                deq_event = active_in_flight[flight_key].pop(0)
                flight = PacketFlight(
                    pkt_id=pkt_id,
                    flow_id=flow_id,
                    src=src,
                    dst=dst,
                    pkt_type=pkt_type,
                    size=size,
                    color_id=color_id,
                    t_start=deq_event.time,
                    t_end=max(time_val, deq_event.time + 1e-5),
                    was_dropped=True,
                    drop_time=time_val
                )
                data.flights.append(flight)
            
            # Record explicit drop event for particle / marker animation
            data.drops.append(DropEvent(
                time=time_val,
                src=src,
                dst=dst,
                pkt_id=pkt_id,
                pkt_type=pkt_type,
                color_id=color_id,
                x=drop_x,
                y=drop_y
            ))

    # Any remaining dequeued packets that never received an explicit 'r' or 'd' (e.g. simulation ended)
    for (pkt_id, src, dst), deq_list in active_in_flight.items():
        link = data.links.get((src, dst))
        est_delay = link.delay if link else 0.02
        for deq_event in deq_list:
            flight = PacketFlight(
                pkt_id=pkt_id,
                flow_id=deq_event.flow_id,
                src=src,
                dst=dst,
                pkt_type=deq_event.pkt_type,
                size=deq_event.size,
                color_id=deq_event.color_id,
                t_start=deq_event.time,
                t_end=deq_event.time + est_delay,
                was_dropped=False
            )
            data.flights.append(flight)
            if flight.t_end > max_t:
                max_t = flight.t_end

    # Sort flights chronologically by t_start
    data.flights.sort(key=lambda f: f.t_start)
    data.events.sort(key=lambda e: e.time)
    data.drops.sort(key=lambda d: d.time)

    data.min_time = min_t if min_t != float('inf') else 0.0
    data.max_time = max_t if max_t > 0 else 10.0
    data.total_packets = len(data.flights)

    return data
