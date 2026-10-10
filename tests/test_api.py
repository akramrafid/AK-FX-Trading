"""
Tests for the local Python REST + WebSocket API server.
"""

import json
import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.server import EventBus, BridgeController, APIHandler, json_response


class TestAPIServerComponents(unittest.TestCase):
    def test_json_response_handles_decimals(self):
        from decimal import Decimal
        data = {"price": Decimal("1.13740"), "magic": 92410251}
        encoded = json_response(data)
        decoded = json.loads(encoded.decode("utf-8"))
        self.assertEqual(decoded["price"], 1.1374)
        self.assertEqual(decoded["magic"], 92410251)

    def test_event_bus_broadcast_no_clients(self):
        bus = EventBus()
        # Should execute silently without throwing
        bus.broadcast("test_event", {"hello": "world"})

    def test_bridge_controller_status(self):
        bus = EventBus()
        controller = BridgeController(bus)
        status = controller.get_status()
        self.assertIn("bridge_running", status)
    def test_bridge_controller_halt_and_resume(self):
        bus = EventBus()
        controller = BridgeController(bus)
        
        from risk.guardrails import RiskGuardrails
        guardrails = RiskGuardrails()
        mock_bridge = type("MockBridge", (), {"risk_guardrails": guardrails, "symbol": "USDCADm"})()
        controller._bridges = [mock_bridge]
        controller._bridge = mock_bridge

        # Halt
        res = controller.emergency_halt()
        self.assertTrue(res["emergency_halt"])
        self.assertTrue(guardrails.limits.emergency_halt)
        status = controller.get_status()
        self.assertTrue(status["emergency_halt"])
        
        # Resume
        res = controller.resume()
        self.assertFalse(res["emergency_halt"])
        self.assertFalse(guardrails.limits.emergency_halt)
        status = controller.get_status()
        self.assertFalse(status["emergency_halt"])

    def test_http_server_endpoints(self):
        import urllib.request
        from api.server import create_api_server
        
        # Spin up test server on random port
        bus = EventBus()
        controller = BridgeController(bus)
        server = create_api_server(host="127.0.0.1", port=0, controller=controller)
        port = server.server_address[1]
        
        import threading
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        
        try:
            # Test GET /api/status
            url = f"http://127.0.0.1:{port}/api/status"
            with urllib.request.urlopen(url, timeout=8) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertIn("bridge_running", body)
                self.assertIn("watchdog_state", body)

            # Test GET /api/account
            url = f"http://127.0.0.1:{port}/api/account"
            with urllib.request.urlopen(url, timeout=8) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertIn("balance", body)

            # Test POST /api/bridge/halt
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/bridge/halt",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertTrue(body["emergency_halt"])

            # Test POST /api/bridge/resume
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/bridge/resume",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertFalse(body["emergency_halt"])

            # Test POST /api/mt4/launch
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/mt4/launch",
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertIn("status", body)
                self.assertIn("mt4_running", body)

        finally:
            server.shutdown()
            server.server_close()

    def test_mt4_process_helpers(self):
        from unittest.mock import patch
        from api.server import is_mt4_running, launch_mt4_terminal

        # Test is_mt4_running positive
        with patch("subprocess.check_output", return_value="terminal.exe 12345 Console 1 45,000 K"):
            self.assertTrue(is_mt4_running())

        # Test is_mt4_running negative
        with patch("subprocess.check_output", return_value="INFO: No tasks are running which match the specified criteria."):
            self.assertFalse(is_mt4_running())

        # Test launch_mt4_terminal when already running
        with patch("api.server.is_mt4_running", return_value=True):
            self.assertTrue(launch_mt4_terminal())

        # Test launch_mt4_terminal when not running with valid mock path
        from pathlib import Path
        with patch("api.server.is_mt4_running", return_value=False), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch("os.startfile", create=True) as mock_startfile, \
             patch("time.sleep"):
            res = launch_mt4_terminal(custom_path=Path("C:/fake/terminal.exe"))
            self.assertTrue(res)


if __name__ == "__main__":
    unittest.main()
