"""
engine.py - Simulation Time Engine & State Manager for NS2 NAM visualizer.

Controls the simulation clock, handles playback speed scaling, seeking,
and calculates the exact interpolated (X, Y) positions of all active packets in transit.
"""

import bisect
import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from parser import NamData, Node, Link, PacketFlight, DropEvent


@dataclass
class RenderPacket:
    pkt_id: int
    flow_id: int
    src: int
    dst: int
    pkt_type: str
    size: int
    color_id: str
    x: float
    y: float
    progress: float       # 0.0 to 1.0
    was_dropped: bool
    angle: float          # movement direction angle in radians


@dataclass
class ActiveDrop:
    pkt_id: int
    pkt_type: str
    color_id: str
    x: float
    y: float
    age: float            # Seconds elapsed since drop occurred (sim time)
    fraction: float       # 0.0 (just dropped) to 1.0 (fade out)


class SimulationEngine:
    SPEED_PRESETS = [0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0]

    def __init__(self, data: NamData):
        self.data = data
        self.min_time = data.min_time
        self.max_time = max(data.max_time, data.min_time + 1.0)
        self.current_time = self.min_time
        self.is_paused = False
        self.playback_speed = 1.0
        self.speed_idx = self.SPEED_PRESETS.index(1.0)

        # Pre-extract start times for binary search
        self._flight_starts = [f.t_start for f in self.data.flights]
        self._drop_times = [d.time for d in self.data.drops]

        # Queue tracking: Enqueue events with corresponding dequeue times
        # List of (t_enq, t_deq, src, dst, pkt_id)
        self._queue_intervals: List[Tuple[float, float, int, int, int]] = []
        self._build_queue_intervals()

    def _build_queue_intervals(self):
        """Pairs '+' enqueue events with '-' dequeue events to track buffer occupancy."""
        # Map: (pkt_id, src, dst) -> enqueue event time
        enq_map: Dict[Tuple[int, int, int], List[float]] = {}
        for ev in self.data.events:
            key = (ev.pkt_id, ev.src, ev.dst)
            if ev.event_type == '+':
                if key not in enq_map:
                    enq_map[key] = []
                enq_map[key].append(ev.time)
            elif ev.event_type in ('-', 'd'):
                if key in enq_map and enq_map[key]:
                    t_enq = enq_map[key].pop(0)
                    self._queue_intervals.append((t_enq, ev.time, ev.src, ev.dst, ev.pkt_id))

        self._queue_intervals.sort(key=lambda item: item[0])

    def play(self):
        self.is_paused = False

    def pause(self):
        self.is_paused = True

    def toggle_pause(self):
        self.is_paused = not self.is_paused

    def speed_up(self):
        if self.speed_idx < len(self.SPEED_PRESETS) - 1:
            self.speed_idx += 1
            self.playback_speed = self.SPEED_PRESETS[self.speed_idx]

    def slow_down(self):
        if self.speed_idx > 0:
            self.speed_idx -= 1
            self.playback_speed = self.SPEED_PRESETS[self.speed_idx]

    def set_speed(self, speed: float):
        self.playback_speed = max(0.01, speed)
        # Find closest preset index
        closest_idx = min(range(len(self.SPEED_PRESETS)), key=lambda i: abs(self.SPEED_PRESETS[i] - self.playback_speed))
        self.speed_idx = closest_idx

    def seek(self, target_time: float):
        self.current_time = max(self.min_time, min(self.max_time, target_time))

    def step(self, dt_sim: float):
        self.seek(self.current_time + dt_sim)

    def reset(self):
        self.current_time = self.min_time
        self.is_paused = False

    def update(self, dt_wall_sec: float):
        """Advance simulation clock by dt_wall_sec * playback_speed."""
        if not self.is_paused:
            self.current_time += dt_wall_sec * self.playback_speed
            if self.current_time >= self.max_time:
                self.current_time = self.max_time
                self.is_paused = True

    def get_active_packets(self, lane_offset_pixels: float = 6.0) -> List[RenderPacket]:
        """
        Returns all packets currently traveling between nodes at current_time.
        Interpolates (x, y) coordinates and applies lane offset for opposing traffic.
        """
        t = self.current_time
        active: List[RenderPacket] = []

        # Binary search for flights that started on or before current_time
        idx_end = bisect.bisect_right(self._flight_starts, t)

        for i in range(idx_end):
            flight = self.data.flights[i]
            if flight.t_end < t:
                continue
            if flight.t_start > t:
                continue

            duration = flight.t_end - flight.t_start
            if duration <= 1e-9:
                alpha = 1.0
            else:
                alpha = (t - flight.t_start) / duration
                alpha = max(0.0, min(1.0, alpha))

            src_node = self.data.nodes.get(flight.src)
            dst_node = self.data.nodes.get(flight.dst)
            if not src_node or not dst_node:
                continue

            # Linear interpolation
            base_x = src_node.x + alpha * (dst_node.x - src_node.x)
            base_y = src_node.y + alpha * (dst_node.y - src_node.y)

            # Perpendicular lane offset so A->B and B->A don't overlap
            dx = dst_node.x - src_node.x
            dy = dst_node.y - src_node.y
            dist = math.sqrt(dx * dx + dy * dy)
            angle = math.atan2(dy, dx)

            if dist > 1e-5 and lane_offset_pixels > 0:
                # Perpendicular normal vector pointing to the right of movement direction
                nx = -dy / dist
                ny = dx / dist
                off_x = base_x + nx * lane_offset_pixels
                off_y = base_y + ny * lane_offset_pixels
            else:
                off_x = base_x
                off_y = base_y

            active.append(RenderPacket(
                pkt_id=flight.pkt_id,
                flow_id=flight.flow_id,
                src=flight.src,
                dst=flight.dst,
                pkt_type=flight.pkt_type,
                size=flight.size,
                color_id=flight.color_id,
                x=off_x,
                y=off_y,
                progress=alpha,
                was_dropped=flight.was_dropped,
                angle=angle
            ))

        return active

    def get_active_drops(self, window_sec: float = 0.35) -> List[ActiveDrop]:
        """
        Returns packet drops that occurred within [current_time - window_sec, current_time].
        Used to render drop animations (expanding red burst/cross).
        """
        t = self.current_time
        active_drops: List[ActiveDrop] = []
        if not self.data.drops:
            return active_drops

        t_min_window = max(self.min_time, t - window_sec)
        idx_start = bisect.bisect_left(self._drop_times, t_min_window)
        idx_end = bisect.bisect_right(self._drop_times, t)

        for i in range(idx_start, idx_end):
            drop = self.data.drops[i]
            age = t - drop.time
            if 0.0 <= age <= window_sec:
                fraction = age / window_sec
                active_drops.append(ActiveDrop(
                    pkt_id=drop.pkt_id,
                    pkt_type=drop.pkt_type,
                    color_id=drop.color_id,
                    x=drop.x,
                    y=drop.y,
                    age=age,
                    fraction=fraction
                ))

        return active_drops

    def get_queue_occupancy(self) -> Dict[Tuple[int, int], int]:
        """
        Returns the number of packets currently queued at node `src` waiting
        for transmission across link `(src, dst)` at current_time.
        """
        t = self.current_time
        occupancy: Dict[Tuple[int, int], int] = {}

        for (t_enq, t_deq, src, dst, _) in self._queue_intervals:
            if t_enq <= t < t_deq:
                key = (src, dst)
                occupancy[key] = occupancy.get(key, 0) + 1
            elif t_enq > t:
                # Since intervals are sorted by t_enq, we can break early
                break

        return occupancy
