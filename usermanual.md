# NS2 NAM Visualizer: Complete End-to-End User Manual

This manual provides an end-to-end guide for creating network simulations in **Network Simulator 2 (NS2)**, generating `.nam` trace files, and animating them using the **Modern Python 3 / Pygame NAM Visualizer**.

---

## Table of Contents
1. [Overview & Why This Tool Exists](#1-overview--why-this-tool-exists)
2. [Phase 1: Writing the NS2 TCL Script from Scratch](#2-phase-1-writing-the-ns2-tcl-script-from-scratch)
   - [Step 1: Open a Text Editor](#step-1-open-a-text-editor)
   - [Step 2: Anatomy of a TCL Simulation Script](#step-2-anatomy-of-a-tcl-simulation-script)
   - [Step 3: Complete Ready-to-Run TCL Script (`simulation.tcl`)](#step-3-complete-ready-to-run-tcl-script-simulationtcl)
3. [Phase 2: Generating the `.nam` Trace File](#3-phase-2-generating-the-nam-trace-file)
   - [Running the Script with NS2](#running-the-script-with-ns2)
   - [Understanding the Legacy NAM Problem](#understanding-the-legacy-nam-problem)
4. [Phase 3: Visualizing with the Modern NAM Visualizer](#4-phase-3-visualizing-with-the-modern-nam-visualizer)
   - [Installation & Setup](#installation--setup)
   - [Launching the Visualizer](#launching-the-visualizer)
5. [User Interface & Interactive Controls](#5-user-interface--interactive-controls)
   - [On-Screen Control Bar & Timeline Scrubber](#on-screen-control-bar--timeline-scrubber)
   - [Mouse Controls (Zoom & Pan)](#mouse-controls-zoom--pan)
   - [Complete Keyboard Shortcuts](#complete-keyboard-shortcuts)
   - [Inspecting Nodes & Packets (Tooltips)](#inspecting-nodes--packets-tooltips)
6. [Visual Elements & What You Are Seeing](#6-visual-elements--what-you-are-seeing)
7. [Behind the Scenes: Architectural Components](#7-behind-the-scenes-architectural-components)
8. [Automated Verification & Unit Tests](#8-automated-verification--unit-tests)
9. [Troubleshooting & FAQs](#9-troubleshooting--faqs)

---

## 1. Overview & Why This Tool Exists

In networking courses and research, **Network Simulator 2 (NS2)** is used to simulate routing protocols, queue management, and transport layer behaviors (TCP, UDP, CBR). 

Traditionally, NS2 outputs an animation trace file ending in `.nam`, which was animated using the legacy **NAM** application. However, legacy NAM relies on decades-old Tcl/Tk and X11 graphics libraries that frequently crash on modern 64-bit Linux distributions (Ubuntu 20.04+, Debian, Fedora, Arch) with:
- Segmentation faults (`SIGSEGV`)
- Display server incompatibilities (Wayland / modern Xorg)
- Lack of modern controls (no timeline scrubber, no smooth zoom or pan)

This tool is a native **Python 3 + Pygame** animator that directly parses any NS2 `.nam` trace file and provides a smooth 60 FPS interactive visualizer.

---

## 2. Phase 1: Writing the NS2 TCL Script from Scratch

### Step 1: Open a Text Editor
You can write your simulation script using **Notepad++** (on Windows) or any text editor on Linux (such as **VS Code**, **Gedit**, **Nano**, or **Vim**).

Save your file with a `.tcl` extension, for example: `simulation.tcl`.

---

### Step 2: Anatomy of a TCL Simulation Script

Every NS2 script requires five key sections to output a `.nam` animation file:

1. **Simulator Initialization**:
   Creates the simulator engine and opens a writable `.nam` file.
   ```tcl
   set ns [new Simulator]
   set nf [open out.nam w]
   $ns namtrace-all $nf
   ```

2. **Node Creation**:
   Creates the network entities.
   ```tcl
   set n0 [$ns node]
   set n1 [$ns node]
   set n2 [$ns node]
   ```

3. **Link Creation & Layout**:
   Defines connections between nodes, their bandwidth, propagation delay, and queue discipline (e.g. `DropTail`, `RED`).
   ```tcl
   $ns duplex-link $n0 $n1 2Mb 10ms DropTail
   $ns duplex-link $n1 $n2 1Mb 20ms DropTail
   ```

4. **Traffic Agent Setup & Scheduling**:
   Attaches protocols (TCP/UDP) and traffic sources (FTP/CBR) to nodes, then connects them.
   ```tcl
   # Set up a TCP agent on n0 and a sink on n2
   set tcp [new Agent/TCP]
   $ns attach-agent $n0 $tcp
   set sink [new Agent/TCPSink]
   $ns attach-agent $n2 $sink
   $ns connect $tcp $sink

   # Attach FTP traffic over TCP
   set ftp [new Application/FTP]
   $ftp attach-agent $tcp

   # Schedule start and stop times (in seconds)
   $ns at 0.5 "$ftp start"
   $ns at 4.0 "$ftp stop"
   ```

5. **Finish Procedure**:
   Flushes trace data, closes the file, and terminates simulation.
   ```tcl
   proc finish {} {
       global ns nf
       $ns flush-trace
       close $nf
       exit 0
   }
   $ns at 4.5 "finish"
   $ns run
   ```

---

### Step 3: Complete Ready-to-Run TCL Script (`simulation.tcl`)

Here is a complete, copy-pasteable TCL script showing a 4-node client-router-server network with a bottleneck link, packet drops, and return ACKs:

```tcl
# =====================================================================
# NS2 Simulation Script: 4-Node Bottleneck Network
# Save this file as: simulation.tcl
# =====================================================================

# 1. Initialize Simulator
set ns [new Simulator]

# Set color IDs for NAM visualizer
$ns color 1 Red
$ns color 2 Blue
$ns color 3 Green

# Open the NAM trace output file
set nf [open out.nam w]
$ns namtrace-all $nf

# Open standard trace file for logging
set tf [open out.tr w]
$ns trace-all $tf

# 2. Define Finish Procedure
proc finish {} {
    global ns nf tf
    $ns flush-trace
    close $nf
    close $tf
    puts "Simulation finished. Output saved to out.nam"
    exit 0
}

# 3. Create 4 Nodes
set n0 [$ns node]
set n1 [$ns node]
set n2 [$ns node]
set n3 [$ns node]

# 4. Create Links (n0 and n1 connect to router n2; n2 connects to n3)
# n0 --(10Mb, 5ms)--> n2 --(1Mb, 30ms Bottleneck)--> n3
# n1 --(10Mb, 5ms)--> n2
$ns duplex-link $n0 $n2 10Mb 5ms DropTail
$ns duplex-link $n1 $n2 10Mb 5ms DropTail
$ns duplex-link $n2 $n3 1Mb 30ms DropTail

# Set queue limit on bottleneck link to demonstrate buffer overflow drops
$ns queue-limit $n2 $n3 5

# Set link orientations for visual layout
$ns duplex-link-op $n0 $n2 orient right-down
$ns duplex-link-op $n1 $n2 orient right-up
$ns duplex-link-op $n2 $n3 orient right

# 5. Set up Flow 1: TCP from n0 to n3 (Red)
set tcp0 [new Agent/TCP]
$tcp0 set class_ 1
$ns attach-agent $n0 $tcp0
set sink0 [new Agent/TCPSink]
$ns attach-agent $n3 $sink0
$ns connect $tcp0 $sink0
set ftp0 [new Application/FTP]
$ftp0 attach-agent $tcp0

# 6. Set up Flow 2: CBR over UDP from n1 to n3 (Blue)
set udp1 [new Agent/UDP]
$udp1 set class_ 2
$ns attach-agent $n1 $udp1
set null1 [new Agent/Null]
$ns attach-agent $n3 $null1
$ns connect $udp1 $null1
set cbr1 [new Application/Traffic/CBR]
$cbr1 set packetSize_ 1000
$cbr1 set rate_ 800Kb
$cbr1 attach-agent $udp1

# 7. Schedule Events
$ns at 0.1 "$cbr1 start"
$ns at 0.5 "$ftp0 start"
$ns at 3.5 "$ftp0 stop"
$ns at 4.0 "$cbr1 stop"
$ns at 4.5 "finish"

# 8. Run the Simulation
$ns run
```

---

## 3. Phase 2: Generating the `.nam` Trace File

### Running the Script with NS2
Run the TCL script using the `ns` command in your terminal:
```bash
ns simulation.tcl
```

When execution completes, you will see:
```text
Simulation finished. Output saved to out.nam
```
Your workspace now contains `out.nam`.

### Understanding the Legacy NAM Problem
If you attempt to run the legacy visualizer on modern Linux:
```bash
nam out.nam
```
It typically fails with:
```text
Segmentation fault (core dumped)
# OR
no display name and no $DISPLAY environment variable / X11 BadWindow error
```
**This is where the new visualizer comes in.**

---

## 4. Phase 3: Visualizing with the Modern NAM Visualizer

### Installation & Setup
Make sure you have Python 3 and Pygame installed:
```bash
pip install pygame
```

### Launching the Visualizer
To view the simulation trace you just generated, run:
```bash
python3 main.py out.nam
```

If you do not specify a file, `main.py` automatically opens the bundled bottleneck demo:
```bash
python3 main.py
```

You can also run any of the sample scenarios:
```bash
python3 main.py sample_basic.nam
python3 main.py sample_tcp_bottleneck.nam
python3 main.py sample_mesh_no_coords.nam
```

---

## 5. User Interface & Interactive Controls

The visualizer provides a modern desktop application interface:

```
+-------------------------------------------------------------------------------------------------------+
| [Legend: TCP / ACK / CBR]                                                   (Node Hover Tooltip)     |
|                                                                                                       |
|      (n0) ---------\                                                                                  |
|                     (n2) ========================== (n3)                                              |
|      (n1) ---------/                                                                                  |
|                                                                                                       |
+-------------------------------------------------------------------------------------------------------+
|  [======================o==============================================================] (Scrubber) |
|                                                                                                       |
|  [|<] [-0.1s] [Pause] [+0.1s]   [-] [1.0x] [+]   Time: 00.245s / 04.500s   [Help (?)]  [Fit View]     |
|                                                  In flight: 4   Drops: 2                              |
+-------------------------------------------------------------------------------------------------------+
```

### On-Screen Control Bar & Timeline Scrubber
- **Interactive Scrubber**: The cyan horizontal bar at the bottom reflects simulation progress. Click or drag the white circle handle to scrub to any point in time.
- **`[|<]` (Reset)**: Jumps back to simulation start ($t = 0.0s$).
- **`[-0.1s]` / `[+0.1s]`**: Steps backward or forward in time by $0.1$ seconds.
- **`[Play]` / `[Pause]`**: Starts or pauses the real-time simulation clock.
- **`[-]` / `[+]` Speed Controls**: Changes simulation speed from $0.05\times$ (slow motion) up to $50.0\times$ (ultra fast).
- **Speed Badge (e.g. `[1.0x]`)**: Click directly to cycle through preset speeds.
- **`[Fit View]`**: Centers and resizes the network to fit your window.
- **`[Help (?)]`**: Toggles the keyboard shortcut cheat-sheet.

---

### Mouse Controls (Zoom & Pan)
- **Zoom In / Out**: Rotate the **Mouse Scroll Wheel**. The visualizer zooms centered directly at your mouse pointer.
- **Pan Canvas**: Hold **Left Click**, **Middle Click**, or **Right Click** and drag anywhere on the canvas to move your view.
- **Hover Inspection**: Move your cursor over any node or packet to inspect details.

---

### Complete Keyboard Shortcuts

| Key | Action | Description |
| :--- | :--- | :--- |
| **`Spacebar`** | Play / Pause | Toggles simulation playback |
| **`→` (Right Arrow)** or **`L`** | Step Forward | Advances simulation clock by `+0.05s` |
| **`←` (Left Arrow)** or **`J`** | Step Backward | Rewinds simulation clock by `-0.05s` |
| **`↑` (Up Arrow)** or **`K`** | Speed Up | Increases playback speed multiplier |
| **`↓` (Down Arrow)** or **`M`** | Slow Down | Decreases playback speed multiplier |
| **`Home`** or **`R`** | Restart | Resets simulation back to $t_{start}$ |
| **`F`** | Auto-Fit | Fits and centers the network topology inside the window |
| **`H`** or **`?`** | Help | Toggles the keyboard shortcut modal overlay |
| **`Esc`** or **`Q`** | Quit | Closes the visualizer |

---

### Inspecting Nodes & Packets (Tooltips)

- **Hovering over a Node shows**:
  - Node Label (e.g., `Client 1`, `Router`, or `n0`)
  - Node ID
  - World Coordinates $(x, y)$
- **Hovering over a moving Packet shows**:
  - Packet ID (`#3`) and Flow ID
  - Protocol Type (`TCP`, `CBR`, `ACK`)
  - Payload Size (e.g. `1040 Bytes`)
  - Trajectory (`n0 -> n2`) and journey progress percentage (`64%`)

---

## 6. Visual Elements & What You Are Seeing

1. **Nodes**:
   - Drawn as circular dark hubs with bright cyan borders and centered labels.
   - When hovered, nodes glow golden.
2. **Links & Bidirectional Lanes**:
   - Links connect nodes with smooth antialiased lines.
   - When packets travel in opposite directions simultaneously (e.g. Data forward and ACKs backward), packets are rendered with a **perpendicular lane offset** so opposing traffic never collides visually.
3. **Packet Protocols & Colors**:
   - **TCP Packets**: Coral Red
   - **ACK Packets**: Emerald Green
   - **CBR / UDP Packets**: Sky Blue
   - **Other Flows**: Mapped from the trace file's `-c <color_id>` tag.
4. **Queue Buffer Badges**:
   - When packets are enqueued at a node waiting for link availability, a golden circular badge appears at the node's link interface displaying the current queue size (e.g. `3`).
5. **Drop Shockwaves**:
   - When a packet is dropped due to queue overflow, an expanding red shockwave ring appears with an **"X"** marker at the drop location, fading over $0.4$ seconds.

---

## 7. Behind the Scenes: Architectural Components

The visualizer codebase is organized into three clean, decoupled Python modules:

### 1. `parser.py` (The Parser)
- Iterates line-by-line over `.nam` files using key-value tag parsing (`-flag value`).
- Pairs packet dequeue (`-`) events with matching receive (`r`) or drop (`d`) events into complete flight intervals `[t_start, t_end]`.
- **Automatic Fallback Layout Engine**: If your TCL script did not specify coordinates (`-x`, `-y`), `parser.py` runs a spring-embedder force-directed layout algorithm so your topology is always rendered neatly.

### 2. `engine.py` (The Time Engine & State Manager)
- Maintains the master animation clock.
- Uses binary search (`bisect`) over sorted departure times, allowing instantaneous seeking and 60 FPS performance even with tens of thousands of packets.
- Computes exact interpolated coordinates $\vec{P}(t)$ for all active packets at the current simulation timestamp.

### 3. `main.py` (The Renderer)
- Pygame-based double-buffered graphics engine.
- Handles responsive window resizing, camera zoom/pan coordinate transformation matrices, UI button dispatching, and particle rendering.

---

## 8. Automated Verification & Unit Tests

The visualizer includes a built-in unit test suite covering the parser, coordinate calculations, and the time engine.

To run the automated tests:
```bash
python3 test_parser_engine.py
```

Expected output:
```text
........
----------------------------------------------------------------------
Ran 8 tests in 0.005s

OK
```

---

## 9. Troubleshooting & FAQs

### Q1: My nodes are all overlapping at the center of the screen.
- **Cause**: Some older NS2 scripts do not assign `-x` and `-y` coordinates.
- **Solution**: The parser automatically calculates clean positions using its built-in spring layout. Press **`F`** to auto-fit, or use the **Mouse Scroll Wheel** to zoom in.

### Q2: Packets move too quickly to observe.
- **Solution**: Press **`↓` (Down Arrow)** to decrease the speed to `0.25x`, `0.1x`, or `0.05x`. You can also press **`Spacebar`** to pause and tap **`→`** to step forward $0.05$ seconds at a time.

### Q3: How do I jump directly to the packet drops?
- **Solution**: Drag the **Timeline Scrubber** handle at the bottom of the screen. Watch the **Drops** counter in the bottom status panel to find the exact moment drops occur.

### Q4: Does this work on headless servers or CI/CD?
- **Solution**: Yes. You can run tests or headless exports by setting `SDL_VIDEODRIVER=dummy`:
  ```bash
  SDL_VIDEODRIVER=dummy python3 test_parser_engine.py
  ```
