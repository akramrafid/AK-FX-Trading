"""
Tests for the local Python REST + WebSocket API server.
"""

import json
import unittest
from unittest.mock import MagicMock
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
        
        # Halt
        res = controller.emergency_halt()
        self.assertTrue(res["emergency_halt"])
        status = controller.get_status()
        self.assertTrue(status["emergency_halt"])
        
        # Resume
        res = controller.resume()
        self.assertFalse(res["emergency_halt"])
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
            with urllib.request.urlopen(url, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertIn("bridge_running", body)
                self.assertIn("watchdog_state", body)

            # Test GET /api/account
            url = f"http://127.0.0.1:{port}/api/account"
            with urllib.request.urlopen(url, timeout=3) as resp:
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
            with urllib.request.urlopen(req, timeout=3) as resp:
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
            with urllib.request.urlopen(req, timeout=3) as resp:
                self.assertEqual(resp.status, 200)
                body = json.loads(resp.read().decode("utf-8"))
                self.assertFalse(body["emergency_halt"])

        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
