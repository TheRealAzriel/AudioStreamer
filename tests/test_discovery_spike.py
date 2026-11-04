import json
import socket
import threading
import time
import unittest
from unittest.mock import Mock, patch

from discovery_spike import (
    CAPABILITY, MAX_PACKET, MAX_RECEIVED, MAX_RESULTS, PORT, ProtocolError, decode_packet,
    discover, encode_packet, parse_request, parse_response, request_packet,
    response_packet, serve,
)


NONCE = "0123456789abcdef0123456789abcdef"


class DiscoveryProtocolTests(unittest.TestCase):
    def test_request_response_round_trip(self):
        request = request_packet(NONCE)
        self.assertEqual(parse_request(request), NONCE)
        response = response_packet(NONCE, "Office: Speakers", "192.168.1.20")
        receiver = parse_response(response, NONCE, "192.168.1.20")
        self.assertEqual(receiver.name, "Office: Speakers")
        self.assertEqual(receiver.address, "192.168.1.20")
        self.assertEqual(receiver.audio_port, 6005)
        self.assertTrue(receiver.compatible)
        self.assertLessEqual(len(response), MAX_PACKET)

    def test_invalid_requests_are_rejected(self):
        valid = decode_packet(request_packet(NONCE))
        invalid = [
            b"", b"x" * (MAX_PACKET + 1), b"\xff", b"[]", b"null",
            b"{" * MAX_PACKET,
        ]
        for field, value in (
            ("version", True), ("version", 2), ("protocol", "other"),
            ("nonce", "short"), ("nonce", "A" * 32), ("type", "receiver"),
            ("unexpected", True),
        ):
            document = dict(valid)
            document[field] = value
            invalid.append(json.dumps(document).encode())
        for packet in invalid:
            with self.subTest(packet=packet[:60]), self.assertRaises(ProtocolError):
                parse_request(packet)

    def test_malformed_responses_and_stale_nonce_are_rejected(self):
        valid = decode_packet(response_packet(NONCE, "Office", "192.168.1.20"))
        for field, value in (
            ("nonce", "0" * 32), ("name", ""), ("name", "a" * 65),
            ("name", "fake\nlog"), ("address", "192.168.1.99"),
            ("address", "0.0.0.0"), ("address", "::1"),
            ("app_version", 1), ("app_version", "a" * 33),
            ("audio_port", True), ("audio_port", 0), ("audio_port", 65536),
            ("capabilities", "not a list"), ("capabilities", ["x"] * 9),
            ("capabilities", [None]), ("extra", True),
        ):
            document = dict(valid)
            document[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ProtocolError):
                parse_response(json.dumps(document).encode(), NONCE, "192.168.1.20")

    def test_capability_not_app_version_determines_compatibility(self):
        document = decode_packet(response_packet(NONCE, "Office", "192.168.1.20"))
        document["app_version"] = "9.0.0"
        self.assertTrue(parse_response(
            encode_packet(document), NONCE, "192.168.1.20"
        ).compatible)
        document["capabilities"] = ["future-format"]
        self.assertFalse(parse_response(
            encode_packet(document), NONCE, "192.168.1.20"
        ).compatible)
        document["capabilities"] = [CAPABILITY]
        document["audio_port"] = 7000
        self.assertFalse(parse_response(
            encode_packet(document), NONCE, "192.168.1.20"
        ).compatible)

    def test_unicode_name_fits_packet_budget(self):
        packet = response_packet(NONCE, "\U0001f3b5" * 64, "192.168.1.20")
        self.assertLessEqual(len(packet), MAX_PACKET)
        self.assertEqual(parse_response(packet, NONCE, "192.168.1.20").name, "\U0001f3b5" * 64)

    def test_invalid_limits_fail_before_network_activity(self):
        for interfaces, timeout in (
            ([], 2), (["127.0.0.1/8"] * 9, 2),
            (["127.0.0.1/8"], 0), (["127.0.0.1/8"], 6),
            (["127.0.0.1/8"], float("nan")),
        ):
            with self.subTest(interfaces=interfaces, timeout=timeout):
                with patch("discovery_spike.socket.socket") as create:
                    with self.assertRaises(ValueError):
                        discover(interfaces, timeout=timeout)
                    create.assert_not_called()

    def test_only_selected_interface_broadcasts_are_probed(self):
        first, second = Mock(), Mock()
        with (
            patch("discovery_spike.socket.socket", side_effect=[first, second]),
            patch("discovery_spike.time.monotonic", side_effect=[0, 3]),
        ):
            discover(["192.168.10.5/24", "10.1.2.3/16"])
        first.bind.assert_called_once_with(("192.168.10.5", 0))
        second.bind.assert_called_once_with(("10.1.2.3", 0))
        self.assertEqual(first.sendto.call_args.args[1], ("192.168.10.255", PORT))
        self.assertEqual(second.sendto.call_args.args[1], ("10.1.255.255", PORT))
        first.close.assert_called_once()
        second.close.assert_called_once()

    def test_client_bounds_total_packets_and_deduplicates_results(self):
        sock = Mock()
        sock.recvfrom.return_value = (
            response_packet(NONCE, "Office", "127.0.0.1"), ("127.0.0.1", PORT)
        )
        with (
            patch("discovery_spike.socket.socket", return_value=sock),
            patch("discovery_spike.select.select", return_value=([sock], [], [])),
            patch("discovery_spike.secrets.token_hex", return_value=NONCE),
        ):
            results = discover(["127.0.0.1/8"])
        self.assertEqual(sock.recvfrom.call_count, MAX_RECEIVED)
        self.assertEqual(len(results), 1)

    def test_client_bounds_distinct_results(self):
        sock = Mock()
        sock.recvfrom.side_effect = [
            (
                response_packet(NONCE, f"Receiver {index}", f"10.0.0.{index}"),
                (f"10.0.0.{index}", PORT),
            )
            for index in range(1, MAX_RESULTS + 2)
        ]
        with (
            patch("discovery_spike.socket.socket", return_value=sock),
            patch("discovery_spike.select.select", return_value=([sock], [], [])),
            patch("discovery_spike.secrets.token_hex", return_value=NONCE),
        ):
            results = discover(["127.0.0.1/8"])
        self.assertEqual(sock.recvfrom.call_count, MAX_RESULTS)
        self.assertEqual(len(results), MAX_RESULTS)

    def test_packet_limit_includes_rejected_packets_on_all_interfaces(self):
        oversized = OSError("Datagram exceeds receive buffer")
        oversized.winerror = 10040
        for failure in (False, True):
            with self.subTest(oversized=failure):
                sockets = [Mock() for _ in range(3)]
                for sock in sockets:
                    if failure:
                        sock.recvfrom.side_effect = oversized
                    else:
                        sock.recvfrom.return_value = (b"invalid", ("127.0.0.1", PORT))
                with (
                    patch("discovery_spike.socket.socket", side_effect=sockets),
                    patch("discovery_spike.select.select", return_value=(sockets, [], [])),
                ):
                    self.assertEqual(discover(
                        ["127.0.0.1/8", "127.0.0.2/8", "127.0.0.3/8"]
                    ), [])
                self.assertEqual(
                    sum(sock.recvfrom.call_count for sock in sockets), MAX_RECEIVED
                )
                for sock in sockets:
                    sock.close.assert_called_once()

    def test_socket_failure_is_propagated_and_owned_sockets_are_closed(self):
        sock = Mock()
        sock.bind.side_effect = OSError("Selected adapter unavailable")
        with patch("discovery_spike.socket.socket", return_value=sock):
            with self.assertRaisesRegex(OSError, "adapter unavailable"):
                discover(["127.0.0.1/8"])
        sock.close.assert_called_once()


class DiscoverySocketTests(unittest.TestCase):
    def start_responder(self, sock, name="Loopback Receiver"):
        stop = threading.Event()
        ready = threading.Event()
        errors = []

        def run():
            try:
                serve(sock, name, stop, duration=5, ready=ready)
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=run)
        thread.start()

        def cleanup():
            stop.set()
            thread.join(timeout=2)
            sock.close()
            self.assertFalse(thread.is_alive(), "Responder did not stop")
            self.assertEqual(errors, [])

        self.addCleanup(cleanup)
        self.assertTrue(ready.wait(2))
        return stop

    def test_standard_socket_loopback_discovery_without_audio_listener(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        self.start_responder(sock)
        results = discover(["127.0.0.1/8"], port=port, timeout=0.2, unicast=True)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].address, "127.0.0.1")
        self.assertTrue(results[0].compatible)

    def test_two_explicit_interfaces_return_two_distinct_receivers(self):
        first = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        first.bind(("127.0.0.1", 0))
        port = first.getsockname()[1]
        second = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            second.bind(("127.0.0.2", port))
        except OSError:
            first.close()
            second.close()
            raise
        self.start_responder(first, "First")
        self.start_responder(second, "Second")
        receivers = discover(
            ["127.0.0.1/8", "127.0.0.2/8"], port=port, timeout=0.2, unicast=True
        )
        self.assertEqual({item.address for item in receivers}, {"127.0.0.1", "127.0.0.2"})

    def test_duplicates_malformed_and_stale_responses_do_not_pollute_results(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
        errors = []

        def send_responses():
            try:
                server.settimeout(2)
                packet, peer = server.recvfrom(MAX_PACKET + 1)
                nonce = parse_request(packet)
                response = response_packet(nonce, "Office", "127.0.0.1")
                for payload in (
                    b"bad json", response_packet("0" * 32, "Stale", "127.0.0.1"),
                    response, response,
                ):
                    server.sendto(payload, peer)
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=send_responses)
        thread.start()
        try:
            results = discover(["127.0.0.1/8"], port=port, timeout=0.2, unicast=True)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].name, "Office")
        finally:
            thread.join(timeout=3)
            server.close()
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_no_response_times_out_and_cancel_returns_promptly(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as silence:
            silence.bind(("127.0.0.1", 0))
            port = silence.getsockname()[1]
            started = time.monotonic()
            self.assertEqual(discover(
                ["127.0.0.1/8"], port=port, timeout=0.15, unicast=True
            ), [])
            self.assertLess(time.monotonic() - started, 1)
            cancel = threading.Event()
            cancel.set()
            started = time.monotonic()
            self.assertEqual(discover(
                ["127.0.0.1/8"], port=port, cancel=cancel, unicast=True
            ), [])
            self.assertLess(time.monotonic() - started, 0.5)

    def test_responder_ignores_invalid_requests_and_rate_limits(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(("127.0.0.1", 0))
        address = server.getsockname()
        stop = self.start_responder(server)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.bind(("127.0.0.1", 0))
            client.settimeout(0.2)
            client.sendto(b"not discovery", address)
            with self.assertRaises(socket.timeout):
                client.recvfrom(MAX_PACKET + 1)
            for _ in range(40):
                client.sendto(request_packet(NONCE), address)
            responses = 0
            while True:
                try:
                    packet, source = client.recvfrom(MAX_PACKET + 1)
                except socket.timeout:
                    break
                self.assertTrue(parse_response(packet, NONCE, source[0]).compatible)
                responses += 1
            self.assertGreater(responses, 0)
            self.assertLessEqual(responses, 32)
        stop.set()


if __name__ == "__main__":
    unittest.main()
