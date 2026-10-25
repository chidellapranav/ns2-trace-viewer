# NS2 NAM Visualizer: Project Specification

## 1. Objective
Build a local, modern graphical animator that parses Network Simulator 2 (NS2) `.nam` trace files and animates the network events in real-time. This replaces the legacy NAM tool which crashes on modern Linux distributions. 

## 2. Tech Stack
*   **Language:** Python 3.x
*   **Graphics Engine:** Pygame (preferred for 2D canvas drawing) or HTML5 Canvas/JavaScript (if building a web UI).
*   **Dependencies:** Standard libraries (Regex/String parsing) + Pygame.

## 3. Workflow Architecture
The application must be decoupled into three core components:

1.  **The Parser:** Reads the `.nam` file line-by-line and extracts entities (nodes, links) and events (packet queues, drops, receives) into a structured format (e.g., list of dictionaries).
2.  **The Time Engine (State Manager):** Maps the simulation timestamp (`-t`) to a real-time animation loop. It must support scaling (speeding up or slowing down the animation) and manage the current state of all packets in transit.
3.  **The Renderer:** Draws the nodes and links on a 2D grid. Interpolates the position of moving packets between the source and destination nodes based on the elapsed simulation time.

## 4. Understanding the .nam Syntax
The parser must handle the following standard `.nam` trace formats. The file is space-separated.

### A. Initialization Events (Nodes and Links)
*   **Nodes:** `n -t * -s <node_id> -x <X_coord> -y <Y_coord> -Z <Z_coord> -v <shape> -c <color>`
    *   *Example:* `n -t * -s 0 -x 50 -y 50 -Z 0 -v circle -c black`
*   **Links:** `l -t * -s <src_node> -d <dst_node> -S <status> -r <bandwidth> -D <delay>`
    *   *Example:* `l -t * -s 0 -d 1 -S UP -r 1000000 -D 0.01`

### B. Packet Events
Packet events dictate the movement. The flag at the beginning defines the action:
*   `+` : Enqueue (Packet entered the queue at source)
*   `-` : Dequeue (Packet left the queue and is traveling on the link)
*   `r` : Receive (Packet arrived at destination)
*   `d` : Drop (Packet was dropped)

**Packet Event Syntax:**
`<event_type> -t <time> -s <src_node> -d <dst_node> -p <packet_type> -e <size> -c <color_id> -i <packet_id> -a <flow_id>`
*   *Example:* `+ -t 1.250 -s 0 -d 1 -p tcp -e 1000 -c 1 -i 0 -a 1`

## 5. Execution Steps for the AI
1.  **Create `parser.py`:** Write a robust regex or string-splitting parser that iterates through the `.nam` file, ignoring unrecognized lines, and outputs a structured dictionary of nodes, links, and a chronological list of packet events.
2.  **Create `engine.py`:** Implement a logic loop that takes the current "animation clock" time and determines exactly where every active packet should be located on the 2D plane (interpolating X/Y coordinates between source and destination based on departure and arrival times).
3.  **Create `main.py` (Renderer):** Initialize a Pygame window. Draw the static nodes and links. Create the main game loop that ticks the time forward, asks the engine for packet positions, and draws them as colored dots moving across the screen.

## 6. MVP Requirements
*   A window opens showing nodes as circles and links as lines.
*   Packets are represented as small colored dots moving along the links.
*   Playback controls (Play, Pause, Speed Up, Slow Down) are mapped to keyboard inputs (e.g., Spacebar to pause, Left/Right arrows for speed).