# NS2 NAM Visualizer

A modern, fast graphical animator and visualizer for Network Simulator 2 (NS2) `.nam` trace files built with Python 3 and Pygame.

Designed as a drop-in replacement for the legacy NS2 NAM tool, which frequently encounters segmentation faults, library deprecations, or X11 rendering issues on modern Linux systems.

---

## Architecture

The project is decoupled into three core components according to specification:

1. **`parser.py` (Trace Parser)**:
   - Reads `.nam` files line-by-line using key-value tag parsing.
   - Parses node definitions (`n`), link topologies (`l`), color definitions (`c`), and packet actions (`+`, `-`, `r`, `d`).
   - Reconstructs packet flight intervals `[t_depart, t_arrive]` paired by packet ID, source, destination, and flow ID.
   - Built-in **Spring-Embedder Force-Directed Layout**: Automatically generates clean topological coordinates when traces omit `-x` and `-y` node positions.

2. **`engine.py` (Simulation Clock & State Engine)**:
   - Synchronizes simulation timestamps (`-t`) with real-time animation.
   - Supports scaling playback speeds (0.05x to 50.0x) and bidirectional scrubbing.
   - Fast $O(\log N)$ binary search queries to calculate exact 2D interpolated coordinates for all packets in transit.
   - Adds perpendicular lane offsets to prevent visual collision between opposing bidirectional traffic.
   - Tracks dynamic link buffer queue occupancies and recent drop events.

3. **`main.py` (Renderer & User Interface)**:
   - Pygame-based 2D canvas running at 60 FPS.
   - Smooth camera system supporting mouse wheel zoom and click-and-drag pan.
   - Interactive bottom control bar with a draggable timeline scrubber, playback controls, and metrics HUD.
   - Animated packet drop shockwaves and queue occupancy counters.
   - Contextual tooltips on hover for nodes and packets.

---

## Quick Start

### 1. Requirements
Ensure Python 3 and Pygame are installed:
```bash
pip install pygame
```

### 2. Running the Visualizer
You can launch the visualizer with any `.nam` trace file:
```bash
# Run with the TCP bottleneck demo (default)
python3 main.py

# Run with a specific trace file
python3 main.py sample_basic.nam
python3 main.py sample_tcp_bottleneck.nam
python3 main.py sample_mesh_no_coords.nam
python3 main.py /path/to/your/simulation.nam
```

---

## Controls & Keyboard Shortcuts

| Control | Action |
| :--- | :--- |
| **`Space`** | Play / Pause simulation |
| **`←` / `→`** | Step backward / forward (0.05s) |
| **`↑` / `↓`** | Increase / decrease playback speed (0.05x to 50x) |
| **`Home` or `R`** | Restart simulation from the beginning |
| **`F`** | Auto-fit network topology to window |
| **Mouse Wheel** | Zoom in / out centered at cursor position |
| **Left / Right / Middle Drag** | Pan canvas |
| **Timeline Scrubber** | Click or drag slider at bottom to seek to any time |
| **`H` or `?`** | Toggle on-screen keyboard shortcut cheat sheet |
| **`Esc` or `Q`** | Exit visualizer |

---

## Running the Automated Test Suite

Run the unit tests covering parsing, auto-layout, interpolation math, and time stepping:
```bash
python3 test_parser_engine.py
```
