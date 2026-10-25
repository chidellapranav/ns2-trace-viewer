#!/usr/bin/env python3
"""
main.py - Modern NS2 NAM Graphical Visualizer & Animator.

Renders nodes, links, and animated packet flows in real-time using Pygame.
Includes interactive camera controls (zoom & pan), playback timeline scrubber,
speed adjustment, drop particle effects, and inspection tooltips.
"""

import sys
import os
import math
import time
from typing import Dict, List, Optional, Tuple

import pygame
from parser import parse_nam_file, NamData, Node, Link
from engine import SimulationEngine, RenderPacket, ActiveDrop

# Palette definitions
COLOR_BG = (18, 22, 30)           # Dark charcoal/slate
COLOR_CANVAS_GRID = (28, 34, 46)
COLOR_LINK = (70, 80, 100)
COLOR_LINK_ACTIVE = (120, 140, 180)
COLOR_NODE_FILL = (35, 42, 56)
COLOR_NODE_BORDER = (100, 180, 246)
COLOR_NODE_HIGHLIGHT = (255, 215, 0)
COLOR_TEXT_PRIMARY = (240, 244, 250)
COLOR_TEXT_MUTED = (140, 150, 170)
COLOR_PANEL_BG = (14, 17, 24)
COLOR_PANEL_BORDER = (45, 55, 75)
COLOR_SCRUB_BG = (35, 45, 62)
COLOR_SCRUB_FILL = (56, 189, 248)
COLOR_SCRUB_HANDLE = (255, 255, 255)
COLOR_BUTTON_BG = (30, 38, 52)
COLOR_BUTTON_HOVER = (45, 58, 80)
COLOR_BUTTON_ACTIVE = (60, 80, 110)
COLOR_DROP_BURST = (239, 68, 68)

# Protocol colors
PROTOCOL_COLORS = {
    "tcp": (248, 113, 113),      # Coral red
    "ack": (52, 211, 153),       # Emerald green
    "cbr": (56, 189, 248),       # Sky blue
    "udp": (168, 85, 247),       # Purple
    "rtp": (251, 146, 60),       # Orange
}

NAM_INDEX_COLORS = {
    "0": (56, 189, 248),
    "1": (248, 113, 113),
    "2": (52, 211, 153),
    "3": (251, 146, 60),
    "4": (168, 85, 247),
    "5": (20, 184, 166),
    "6": (234, 179, 8),
}

NAM_NAME_COLORS = {
    "red": (248, 113, 113),
    "blue": (56, 189, 248),
    "green": (52, 211, 153),
    "black": (20, 24, 33),
    "white": (240, 244, 250),
    "yellow": (234, 179, 8),
    "orange": (251, 146, 60),
    "purple": (168, 85, 247),
}


def get_packet_color(pkt: RenderPacket, color_table: Dict[str, str]) -> Tuple[int, int, int]:
    """Resolves RGB color for a packet based on protocol, nam color ID, or color table."""
    # Check by color table mapping
    cid = str(pkt.color_id)
    if cid in color_table:
        name_or_hex = color_table[cid].lower()
        if name_or_hex in NAM_NAME_COLORS:
            return NAM_NAME_COLORS[name_or_hex]
        if name_or_hex.startswith("#") and len(name_or_hex) == 7:
            try:
                return (
                    int(name_or_hex[1:3], 16),
                    int(name_or_hex[3:5], 16),
                    int(name_or_hex[5:7], 16)
                )
            except ValueError:
                pass

    if cid in NAM_INDEX_COLORS:
        return NAM_INDEX_COLORS[cid]

    pkt_type = pkt.pkt_type.lower()
    if pkt_type in PROTOCOL_COLORS:
        return PROTOCOL_COLORS[pkt_type]

    return (56, 189, 248)


class Camera:
    """Manages 2D viewport pan, zoom, and coordinate transformations."""
    def __init__(self, viewport_width: int, viewport_height: int):
        self.vw = viewport_width
        self.vh = viewport_height
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.scale = 1.0
        self.is_dragging = False
        self.drag_start = (0, 0)
        self.pan_start = (0.0, 0.0)

    def world_to_screen(self, wx: float, wy: float) -> Tuple[int, int]:
        sx = int(self.pan_x + wx * self.scale)
        sy = int(self.pan_y + wy * self.scale)
        return sx, sy

    def screen_to_world(self, sx: int, sy: int) -> Tuple[float, float]:
        wx = (sx - self.pan_x) / self.scale if self.scale != 0 else 0.0
        wy = (sy - self.pan_y) / self.scale if self.scale != 0 else 0.0
        return wx, wy

    def zoom_at(self, screen_x: int, screen_y: int, factor: float):
        """Zoom centered at cursor position."""
        old_scale = self.scale
        new_scale = max(0.1, min(10.0, old_scale * factor))
        if new_scale == old_scale:
            return

        # Adjust pan so the world coordinate under the cursor remains unchanged
        wx, wy = self.screen_to_world(screen_x, screen_y)
        self.scale = new_scale
        self.pan_x = screen_x - wx * self.scale
        self.pan_y = screen_y - wy * self.scale

    def auto_fit(self, nodes: Dict[int, Node], padding: float = 80.0):
        """Calculates scale and pan to fit all nodes neatly inside viewport."""
        if not nodes:
            self.pan_x = self.vw / 2
            self.pan_y = self.vh / 2
            self.scale = 1.0
            return

        min_x = min(n.x for n in nodes.values())
        max_x = max(n.x for n in nodes.values())
        min_y = min(n.y for n in nodes.values())
        max_y = max(n.y for n in nodes.values())

        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)

        avail_w = max(50.0, self.vw - 2.0 * padding)
        avail_h = max(50.0, self.vh - 2.0 * padding)

        scale_x = avail_w / span_x
        scale_y = avail_h / span_y
        self.scale = min(scale_x, scale_y, 2.5)
        self.scale = max(0.2, self.scale)

        center_wx = (min_x + max_x) / 2.0
        center_wy = (min_y + max_y) / 2.0

        self.pan_x = (self.vw / 2.0) - center_wx * self.scale
        self.pan_y = (self.vh / 2.0) - center_wy * self.scale


class Button:
    def __init__(self, rect: pygame.Rect, label: str, callback, tooltip: str = ""):
        self.rect = rect
        self.label = label
        self.callback = callback
        self.tooltip = tooltip
        self.is_hovered = False

    def handle_event(self, event) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.callback()
                return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        color = COLOR_BUTTON_HOVER if self.is_hovered else COLOR_BUTTON_BG
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        pygame.draw.rect(surface, COLOR_PANEL_BORDER, self.rect, width=1, border_radius=6)

        txt_surf = font.render(self.label, True, COLOR_TEXT_PRIMARY)
        txt_rect = txt_surf.get_rect(center=self.rect.center)
        surface.blit(txt_surf, txt_rect)


class NamVisualizer:
    def __init__(self, nam_file: str, width: int = 1100, height: int = 740):
        pygame.init()
        pygame.font.init()

        self.width = width
        self.height = height
        self.control_bar_height = 80
        self.viewport_height = self.height - self.control_bar_height

        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        self.nam_file = nam_file
        filename = os.path.basename(nam_file)
        pygame.display.set_caption(f"NS2 NAM Visualizer - {filename}")

        self.clock = pygame.time.Clock()
        self.is_running = True
        self.show_help = False

        # Load and parse
        self.data: NamData = parse_nam_file(nam_file)
        self.engine = SimulationEngine(self.data)

        # Fonts
        self.font_sm = pygame.font.Font(None, 18)
        self.font_md = pygame.font.Font(None, 22)
        self.font_lg = pygame.font.Font(None, 26)
        self.font_bold = pygame.font.Font(None, 24)

        # Camera
        self.camera = Camera(self.width, self.viewport_height)
        self.camera.auto_fit(self.data.nodes)

        # UI state
        self.scrubber_rect = pygame.Rect(0, 0, 0, 0)
        self.is_scrubbing = False
        self.hovered_node: Optional[Node] = None
        self.hovered_packet: Optional[RenderPacket] = None
        self.buttons: List[Button] = []
        self._init_buttons()

    def _init_buttons(self):
        """Constructs clickable control buttons in the bottom toolbar."""
        self.buttons.clear()
        y = self.viewport_height + 34
        h = 32

        # Left controls
        bx = 20
        self.buttons.append(Button(pygame.Rect(bx, y, 40, h), "|<", self._btn_reset, "Restart (Home/R)"))
        bx += 46
        self.buttons.append(Button(pygame.Rect(bx, y, 40, h), "-0.1s", lambda: self.engine.step(-0.1), "Step back (Left)"))
        bx += 46
        self.btn_play = Button(pygame.Rect(bx, y, 70, h), "Pause", self._btn_toggle_play, "Play/Pause (Space)")
        self.buttons.append(self.btn_play)
        bx += 76
        self.buttons.append(Button(pygame.Rect(bx, y, 40, h), "+0.1s", lambda: self.engine.step(0.1), "Step fwd (Right)"))

        # Speed controls
        bx += 56
        self.buttons.append(Button(pygame.Rect(bx, y, 32, h), "-", self.engine.slow_down, "Slow down (Down)"))
        bx += 36
        self.btn_speed = Button(pygame.Rect(bx, y, 64, h), f"{self.engine.playback_speed}x", self._btn_cycle_speed, "Speed multiplier")
        self.buttons.append(self.btn_speed)
        bx += 68
        self.buttons.append(Button(pygame.Rect(bx, y, 32, h), "+", self.engine.speed_up, "Speed up (Up)"))

        # Right-aligned controls
        rx = self.width - 100
        self.buttons.append(Button(pygame.Rect(rx, y, 80, h), "Fit View", self._btn_fit, "Fit topology (F)"))
        rx -= 90
        self.buttons.append(Button(pygame.Rect(rx, y, 80, h), "Help (?)", self._btn_toggle_help, "Keyboard Shortcuts (H)"))

    def _btn_toggle_play(self):
        self.engine.toggle_pause()

    def _btn_reset(self):
        self.engine.reset()

    def _btn_fit(self):
        self.camera.auto_fit(self.data.nodes)

    def _btn_toggle_help(self):
        self.show_help = not self.show_help

    def _btn_cycle_speed(self):
        speeds = SimulationEngine.SPEED_PRESETS
        idx = (self.engine.speed_idx + 1) % len(speeds)
        self.engine.set_speed(speeds[idx])

    def resize(self, w: int, h: int):
        self.width = max(800, w)
        self.height = max(500, h)
        self.viewport_height = self.height - self.control_bar_height
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
        self.camera.vw = self.width
        self.camera.vh = self.viewport_height
        self._init_buttons()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.is_running = False
                return

            elif event.type == pygame.VIDEORESIZE:
                self.resize(event.w, event.h)

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    self.engine.toggle_pause()
                elif event.key in (pygame.K_RIGHT, pygame.K_l):
                    self.engine.step(0.05)
                elif event.key in (pygame.K_LEFT, pygame.K_j):
                    self.engine.step(-0.05)
                elif event.key in (pygame.K_UP, pygame.K_k):
                    self.engine.speed_up()
                elif event.key in (pygame.K_DOWN, pygame.K_m):
                    self.engine.slow_down()
                elif event.key in (pygame.K_r, pygame.K_HOME):
                    self.engine.reset()
                elif event.key == pygame.K_f:
                    self.camera.auto_fit(self.data.nodes)
                elif event.key in (pygame.K_h, pygame.K_SLASH):
                    self.show_help = not self.show_help
                elif event.key in (pygame.K_q, pygame.K_ESCAPE):
                    self.is_running = False
                    return

            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                if my < self.viewport_height:
                    factor = 1.15 if event.y > 0 else 0.85
                    self.camera.zoom_at(mx, my, factor)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                if event.button == 1:
                    # Check scrubber hit
                    if self.scrubber_rect.collidepoint(mx, my):
                        self.is_scrubbing = True
                        self._update_scrub(mx)
                    elif my < self.viewport_height:
                        # Start canvas drag pan
                        self.camera.is_dragging = True
                        self.camera.drag_start = (mx, my)
                        self.camera.pan_start = (self.camera.pan_x, self.camera.pan_y)
                elif event.button in (2, 3):  # Middle or Right drag pan
                    if my < self.viewport_height:
                        self.camera.is_dragging = True
                        self.camera.drag_start = (mx, my)
                        self.camera.pan_start = (self.camera.pan_x, self.camera.pan_y)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.is_scrubbing = False
                self.camera.is_dragging = False

            elif event.type == pygame.MOUSEMOTION:
                mx, my = event.pos
                if self.is_scrubbing:
                    self._update_scrub(mx)
                elif self.camera.is_dragging:
                    dx = mx - self.camera.drag_start[0]
                    dy = my - self.camera.drag_start[1]
                    self.camera.pan_x = self.camera.pan_start[0] + dx
                    self.camera.pan_y = self.camera.pan_start[1] + dy

            # Feed to toolbar buttons
            for btn in self.buttons:
                btn.handle_event(event)

    def _update_scrub(self, mx: int):
        frac = (mx - self.scrubber_rect.x) / max(1, self.scrubber_rect.width)
        frac = max(0.0, min(1.0, frac))
        target_t = self.data.min_time + frac * (self.data.max_time - self.data.min_time)
        self.engine.seek(target_t)

    def draw_grid(self):
        """Draws a subtle background grid."""
        step = int(60 * self.camera.scale)
        if step < 25:
            return
        ox = int(self.camera.pan_x) % step
        oy = int(self.camera.pan_y) % step
        for x in range(ox, self.width, step):
            pygame.draw.line(self.screen, COLOR_CANVAS_GRID, (x, 0), (x, self.viewport_height), 1)
        for y in range(oy, self.viewport_height, step):
            pygame.draw.line(self.screen, COLOR_CANVAS_GRID, (0, y), (self.width, y), 1)

    def draw_links(self, queues: Dict[Tuple[int, int], int]):
        """Draws network links between nodes and queue indicators."""
        drawn_undirected = set()

        for (src_id, dst_id), link in self.data.links.items():
            pair = tuple(sorted([src_id, dst_id]))
            src = self.data.nodes.get(src_id)
            dst = self.data.nodes.get(dst_id)
            if not src or not dst:
                continue

            sx1, sy1 = self.camera.world_to_screen(src.x, src.y)
            sx2, sy2 = self.camera.world_to_screen(dst.x, dst.y)

            # Draw the link line once
            if pair not in drawn_undirected:
                drawn_undirected.add(pair)
                # Outer shadow / glow
                pygame.draw.line(self.screen, (32, 38, 50), (sx1, sy1), (sx2, sy2), 4)
                # Main line
                line_color = COLOR_LINK if link.status == "UP" else (180, 50, 50)
                pygame.draw.aaline(self.screen, line_color, (sx1, sy1), (sx2, sy2))
                pygame.draw.line(self.screen, line_color, (sx1, sy1), (sx2, sy2), 2)

            # Queue badge at source end if packets are queued
            q_count = queues.get((src_id, dst_id), 0)
            if q_count > 0:
                dx = sx2 - sx1
                dy = sy2 - sy1
                dist = math.sqrt(dx * dx + dy * dy)
                if dist > 40:
                    qx = int(sx1 + (dx / dist) * 28)
                    qy = int(sy1 + (dy / dist) * 28)
                    badge_rect = pygame.Rect(qx - 9, qy - 9, 18, 18)
                    pygame.draw.circle(self.screen, (234, 179, 8), (qx, qy), 9)
                    q_text = self.font_sm.render(str(q_count), True, (15, 20, 25))
                    self.screen.blit(q_text, q_text.get_rect(center=(qx, qy)))

    def draw_nodes(self):
        """Draws nodes with labels and hover glow."""
        mx, my = pygame.mouse.get_pos()
        self.hovered_node = None
        base_radius = max(14, int(20 * math.sqrt(max(0.5, self.camera.scale))))

        for nid, node in self.data.nodes.items():
            sx, sy = self.camera.world_to_screen(node.x, node.y)

            # Check mouse hover
            dist_mouse = math.hypot(mx - sx, my - sy)
            is_hovered = (dist_mouse <= base_radius + 4) and (my < self.viewport_height)
            if is_hovered:
                self.hovered_node = node

            # Outer ring glow
            border_color = COLOR_NODE_HIGHLIGHT if is_hovered else COLOR_NODE_BORDER
            pygame.draw.circle(self.screen, border_color, (sx, sy), base_radius + 2)

            # Inner circle body
            pygame.draw.circle(self.screen, COLOR_NODE_FILL, (sx, sy), base_radius)

            # Node label inside or above
            label = node.label if node.label else f"n{nid}"
            txt_surf = self.font_bold.render(label, True, COLOR_TEXT_PRIMARY)
            txt_rect = txt_surf.get_rect(center=(sx, sy))
            self.screen.blit(txt_surf, txt_rect)

    def draw_packets(self, packets: List[RenderPacket]):
        """Draws moving packets with directional orientation and glowing borders."""
        mx, my = pygame.mouse.get_pos()
        self.hovered_packet = None

        pkt_radius = max(5, int(7 * math.sqrt(max(0.5, self.camera.scale))))

        for pkt in packets:
            sx, sy = self.camera.world_to_screen(pkt.x, pkt.y)

            # Check hover
            if my < self.viewport_height and math.hypot(mx - sx, my - sy) <= pkt_radius + 4:
                self.hovered_packet = pkt

            color = get_packet_color(pkt, self.data.color_table)

            # Small movement trail or halo
            pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), pkt_radius + 1)
            pygame.draw.circle(self.screen, color, (sx, sy), pkt_radius)

            # Subtle inner highlight
            pygame.draw.circle(self.screen, (255, 255, 255, 120), (sx - 1, sy - 1), max(2, pkt_radius // 2))

    def draw_drops(self, drops: List[ActiveDrop]):
        """Draws animated drop shockwaves and markers."""
        for drop in drops:
            sx, sy = self.camera.world_to_screen(drop.x, drop.y)
            # Expanding radius from 8 to 32 px
            curr_r = int(8 + drop.fraction * 24)
            # Fading alpha
            alpha = int(255 * (1.0 - drop.fraction))
            if alpha <= 0:
                continue

            # Draw expanding shockwave ring
            ring_surf = pygame.Surface((curr_r * 2 + 4, curr_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring_surf, (239, 68, 68, alpha), (curr_r + 2, curr_r + 2), curr_r, width=2)
            self.screen.blit(ring_surf, (sx - curr_r - 2, sy - curr_r - 2))

            # Draw drop cross marker 'X'
            x_size = 5
            pygame.draw.line(self.screen, COLOR_DROP_BURST, (sx - x_size, sy - x_size), (sx + x_size, sy + x_size), 2)
            pygame.draw.line(self.screen, COLOR_DROP_BURST, (sx - x_size, sy + x_size), (sx + x_size, sy - x_size), 2)

    def draw_tooltips(self):
        """Displays contextual hover info for nodes and packets."""
        mx, my = pygame.mouse.get_pos()
        if my >= self.viewport_height:
            return

        lines: List[str] = []
        if self.hovered_node:
            n = self.hovered_node
            lines = [
                f"Node: {n.label} (ID: {n.id})",
                f"Pos: ({n.x:.1f}, {n.y:.1f})",
                f"Shape: {n.shape}"
            ]
        elif self.hovered_packet:
            p = self.hovered_packet
            lines = [
                f"Packet ID: #{p.pkt_id} (Flow: {p.flow_id})",
                f"Type: {p.pkt_type.upper()} | Size: {p.size} B",
                f"Path: n{p.src} -> n{p.dst} ({int(p.progress * 100)}%)"
            ]

        if not lines:
            return

        rendered_lines = [self.font_sm.render(line, True, COLOR_TEXT_PRIMARY) for line in lines]
        tip_w = max(r.get_width() for r in rendered_lines) + 16
        tip_h = sum(r.get_height() for r in rendered_lines) + 14

        tx = min(self.width - tip_w - 10, mx + 15)
        ty = min(self.viewport_height - tip_h - 10, my + 15)
        tip_rect = pygame.Rect(tx, ty, tip_w, tip_h)

        pygame.draw.rect(self.screen, (24, 28, 40), tip_rect, border_radius=6)
        pygame.draw.rect(self.screen, (70, 90, 120), tip_rect, width=1, border_radius=6)

        curr_y = ty + 7
        for r in rendered_lines:
            self.screen.blit(r, (tx + 8, curr_y))
            curr_y += r.get_height()

    def draw_hud_and_controls(self, active_packet_count: int):
        """Draws the bottom control panel, scrubber, metrics, and buttons."""
        panel_y = self.viewport_height
        panel_rect = pygame.Rect(0, panel_y, self.width, self.control_bar_height)

        # Panel background and border
        pygame.draw.rect(self.screen, COLOR_PANEL_BG, panel_rect)
        pygame.draw.line(self.screen, COLOR_PANEL_BORDER, (0, panel_y), (self.width, panel_y), 1)

        # Scrubber bar
        scrub_x = 20
        scrub_y = panel_y + 12
        scrub_w = self.width - 40
        scrub_h = 8
        self.scrubber_rect = pygame.Rect(scrub_x, scrub_y, scrub_w, scrub_h)

        # Background track
        pygame.draw.rect(self.screen, COLOR_SCRUB_BG, self.scrubber_rect, border_radius=4)

        # Progress fill
        total_span = max(1e-5, self.data.max_time - self.data.min_time)
        progress = (self.engine.current_time - self.data.min_time) / total_span
        progress = max(0.0, min(1.0, progress))
        fill_w = int(scrub_w * progress)
        if fill_w > 0:
            fill_rect = pygame.Rect(scrub_x, scrub_y, fill_w, scrub_h)
            pygame.draw.rect(self.screen, COLOR_SCRUB_FILL, fill_rect, border_radius=4)

        # Scrubber thumb
        thumb_x = scrub_x + fill_w
        pygame.draw.circle(self.screen, COLOR_SCRUB_HANDLE, (thumb_x, scrub_y + scrub_h // 2), 7)

        # Update Play/Pause and Speed button labels
        self.btn_play.label = "Play" if self.engine.is_paused else "Pause"
        self.btn_speed.label = f"{self.engine.playback_speed}x"

        # Draw toolbar buttons
        for btn in self.buttons:
            btn.draw(self.screen, self.font_md)

        # Middle HUD metrics: Time, Packets in flight, Drops
        mid_x = 380
        curr_t = self.engine.current_time
        max_t = self.data.max_time
        time_str = f"Time: {curr_t:06.3f}s / {max_t:06.3f}s"
        t_surf = self.font_bold.render(time_str, True, COLOR_TEXT_PRIMARY)
        self.screen.blit(t_surf, (mid_x, panel_y + 36))

        stats_str = f"In flight: {active_packet_count}   Drops: {self.data.total_drops}"
        s_surf = self.font_sm.render(stats_str, True, COLOR_TEXT_MUTED)
        self.screen.blit(s_surf, (mid_x, panel_y + 57))

        # Top-left mini overlay (Filename & Legend)
        self._draw_legend()

    def _draw_legend(self):
        """Displays small protocol color legend in upper corner."""
        lx = 15
        ly = 15
        box_w = 175
        items = [
            ("TCP", PROTOCOL_COLORS["tcp"]),
            ("ACK", PROTOCOL_COLORS["ack"]),
            ("CBR/UDP", PROTOCOL_COLORS["cbr"]),
        ]
        box_h = len(items) * 20 + 28
        legend_rect = pygame.Rect(lx, ly, box_w, box_h)

        # Translucent background
        bg_surf = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        bg_surf.fill((16, 20, 28, 200))
        self.screen.blit(bg_surf, (lx, ly))
        pygame.draw.rect(self.screen, (40, 50, 70), legend_rect, width=1, border_radius=6)

        title = self.font_sm.render("Protocol Legend", True, COLOR_TEXT_MUTED)
        self.screen.blit(title, (lx + 10, ly + 6))

        for idx, (label, color) in enumerate(items):
            iy = ly + 26 + idx * 20
            pygame.draw.circle(self.screen, color, (lx + 18, iy + 6), 5)
            t_item = self.font_sm.render(label, True, COLOR_TEXT_PRIMARY)
            self.screen.blit(t_item, (lx + 32, iy))

    def draw_help_overlay(self):
        """Draws shortcut modal popup when H or ? is pressed."""
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        mw = 520
        mh = 360
        mx = (self.width - mw) // 2
        my = (self.height - mh) // 2
        modal_rect = pygame.Rect(mx, my, mw, mh)

        pygame.draw.rect(self.screen, (22, 28, 40), modal_rect, border_radius=10)
        pygame.draw.rect(self.screen, (70, 90, 130), modal_rect, width=2, border_radius=10)

        title = self.font_lg.render("Keyboard Shortcuts & Navigation", True, COLOR_TEXT_PRIMARY)
        self.screen.blit(title, (mx + 25, my + 20))

        shortcuts = [
            ("Space", "Play / Pause simulation"),
            ("Left / Right", "Step backward / forward (0.05s)"),
            ("Up / Down", "Increase / decrease playback speed"),
            ("Home / R", "Reset simulation to start"),
            ("F", "Auto-fit topology to screen"),
            ("Mouse Wheel", "Zoom in / out centered at cursor"),
            ("Left Drag / Right Drag", "Pan around network canvas"),
            ("Timeline Scrubber", "Click / drag slider to seek time"),
            ("H / ?", "Toggle this help modal"),
            ("Esc / Q", "Exit visualizer")
        ]

        curr_y = my + 60
        for key, desc in shortcuts:
            k_surf = self.font_bold.render(f"[{key}]", True, COLOR_NODE_HIGHLIGHT)
            d_surf = self.font_md.render(desc, True, COLOR_TEXT_PRIMARY)
            self.screen.blit(k_surf, (mx + 30, curr_y))
            self.screen.blit(d_surf, (mx + 190, curr_y))
            curr_y += 26

        close_hint = self.font_sm.render("Press 'H' or 'Esc' to close", True, COLOR_TEXT_MUTED)
        self.screen.blit(close_hint, (mx + mw // 2 - close_hint.get_width() // 2, my + mh - 25))

    def run(self):
        """Main visualizer event and render loop."""
        while self.is_running:
            dt_sec = self.clock.tick(60) / 1000.0

            self.handle_events()
            self.engine.update(dt_sec)

            # Query state from simulation engine
            active_packets = self.engine.get_active_packets(lane_offset_pixels=6.0)
            active_drops = self.engine.get_active_drops(window_sec=0.4)
            queues = self.engine.get_queue_occupancy()

            # Render frame
            self.screen.fill(COLOR_BG)
            self.draw_grid()
            self.draw_links(queues)
            self.draw_nodes()
            self.draw_packets(active_packets)
            self.draw_drops(active_drops)
            self.draw_tooltips()
            self.draw_hud_and_controls(len(active_packets))

            if self.show_help:
                self.draw_help_overlay()

            pygame.display.flip()

        pygame.quit()


def main():
    if len(sys.argv) > 1:
        nam_file = sys.argv[1]
    else:
        # Default fallback to sample
        candidates = ["sample_tcp_bottleneck.nam", "sample_basic.nam", "sample_mesh_no_coords.nam"]
        nam_file = None
        for c in candidates:
            if os.path.exists(c):
                nam_file = c
                break
        if not nam_file:
            print("Usage: python3 main.py <tracefile.nam>")
            sys.exit(1)

    if not os.path.exists(nam_file):
        print(f"Error: file '{nam_file}' not found.")
        sys.exit(1)

    print(f"Loading '{nam_file}'...")
    app = NamVisualizer(nam_file)
    app.run()


if __name__ == "__main__":
    main()
