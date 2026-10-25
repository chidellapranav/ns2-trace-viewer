"""
test_parser_engine.py - Unit test suite for NS2 NAM Parser and Simulation Engine.
"""

import unittest
import math
from parser import parse_nam_file, parse_nam_line, parse_bandwidth, parse_delay
from engine import SimulationEngine


class TestNamParser(unittest.TestCase):
    def test_parse_line(self):
        action, params = parse_nam_line("n -t * -s 0 -x 50.5 -y 100.2 -v circle -c black")
        self.assertEqual(action, "n")
        self.assertEqual(params["s"], "0")
        self.assertEqual(params["x"], "50.5")
        self.assertEqual(params["y"], "100.2")
        self.assertEqual(params["v"], "circle")
        self.assertEqual(params["c"], "black")

    def test_parse_bandwidth_and_delay(self):
        self.assertEqual(parse_bandwidth("1Mb"), 1e6)
        self.assertEqual(parse_bandwidth("100Kb"), 1e5)
        self.assertEqual(parse_bandwidth("2Gb"), 2e9)
        self.assertEqual(parse_bandwidth("500000"), 500000.0)

        self.assertAlmostEqual(parse_delay("10ms"), 0.01)
        self.assertAlmostEqual(parse_delay("1s"), 1.0)
        self.assertAlmostEqual(parse_delay("500us"), 0.0005)

    def test_basic_nam_file(self):
        data = parse_nam_file("sample_basic.nam")
        self.assertEqual(len(data.nodes), 3)
        self.assertIn(0, data.nodes)
        self.assertIn(1, data.nodes)
        self.assertIn(2, data.nodes)
        self.assertTrue(len(data.links) >= 2)
        self.assertTrue(len(data.flights) > 0)
        self.assertEqual(data.total_drops, 1)

    def test_tcp_bottleneck_file(self):
        data = parse_nam_file("sample_tcp_bottleneck.nam")
        self.assertEqual(len(data.nodes), 4)
        self.assertTrue(data.total_drops >= 2)
        self.assertTrue(data.max_time > data.min_time)

    def test_auto_layout(self):
        data = parse_nam_file("sample_mesh_no_coords.nam")
        self.assertEqual(len(data.nodes), 5)
        # Verify nodes received non-zero separated coordinates
        coords = set()
        for node in data.nodes.values():
            coords.add((node.x, node.y))
        self.assertEqual(len(coords), 5, "All 5 nodes should have distinct positions")


class TestSimulationEngine(unittest.TestCase):
    def setUp(self):
        self.data = parse_nam_file("sample_basic.nam")
        self.engine = SimulationEngine(self.data)

    def test_time_and_controls(self):
        self.assertEqual(self.engine.current_time, self.data.min_time)
        self.assertFalse(self.engine.is_paused)

        self.engine.toggle_pause()
        self.assertTrue(self.engine.is_paused)

        # Update while paused should not advance time
        self.engine.update(1.0)
        self.assertEqual(self.engine.current_time, self.data.min_time)

        self.engine.toggle_pause()
        self.engine.update(0.1)
        self.assertAlmostEqual(self.engine.current_time, self.data.min_time + 0.1)

        # Test speed scaling
        self.engine.speed_up()
        self.assertGreater(self.engine.playback_speed, 1.0)
        self.engine.slow_down()
        self.engine.slow_down()
        self.assertLess(self.engine.playback_speed, 1.0)

    def test_packet_interpolation(self):
        # In sample_basic.nam, packet 0 is dequeued at 1.005 and received at 1.025 between node 0 and node 1.
        # Node 0 is at (100, 250), Node 1 is at (350, 250).
        # At mid-time 1.015, packet 0 progress should be 0.5, x ~ (100+350)/2 = 225.
        self.engine.seek(1.015)
        packets = self.engine.get_active_packets(lane_offset_pixels=0.0)
        self.assertTrue(len(packets) >= 1)

        pkt0 = [p for p in packets if p.pkt_id == 0][0]
        self.assertEqual(pkt0.src, 0)
        self.assertEqual(pkt0.dst, 1)
        self.assertAlmostEqual(pkt0.progress, 0.5, places=2)
        self.assertAlmostEqual(pkt0.x, 225.0, places=1)
        self.assertAlmostEqual(pkt0.y, 250.0, places=1)

    def test_drop_detection(self):
        # In sample_basic.nam, a drop occurs at t = 1.380
        self.engine.seek(1.390)
        drops = self.engine.get_active_drops(window_sec=0.2)
        self.assertTrue(len(drops) >= 1)
        drop = drops[0]
        self.assertEqual(drop.pkt_id, 3)
        self.assertAlmostEqual(drop.age, 0.01, places=2)


if __name__ == "__main__":
    unittest.main()
