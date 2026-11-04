"""Standalone discovery prototype; not started by either application."""

import argparse
from collections import deque
from dataclasses import dataclass
import ipaddress
import json
import logging
import math
import secrets
import select
import socket
import threading
import time

from app_settings import APP_VERSION


PORT = 6006
MAX_PACKET = 1024
MAX_RESULTS = 64
MAX_RECEIVED = 256
MAGIC = "audio-streamer-discovery"
CAPABILITY = "tcp-mpegts-mp3-v1"


class ProtocolError(ValueError):
    pass


def unicast_address(value):
    if not isinstance(value, str):
        raise ProtocolError("Address must be IPv4 text.")
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError as exc:
        raise ProtocolError("Invalid IPv4 address.") from exc
    if address.is_unspecified or address.is_multicast or int(address) == 4294967295:
        raise ProtocolError("A unicast IPv4 address is required.")
    return str(address)


def validate_nonce(value):
    if (
        not isinstance(value, str) or len(value) != 32
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ProtocolError("Nonce must contain 32 lowercase hexadecimal characters.")
    return value


def decode_packet(packet):
    if not packet or len(packet) > MAX_PACKET:
        raise ProtocolError("Discovery packet exceeds size bounds.")
    try:
        document = json.loads(packet.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ProtocolError("Invalid discovery JSON.") from exc
    if not isinstance(document, dict):
        raise ProtocolError("Discovery packet must be an object.")
    if document.get("protocol") != MAGIC or type(document.get("version")) is not int:
        raise ProtocolError("Not a supported discovery packet.")
    if document["version"] != 1:
        raise ProtocolError("Unsupported protocol version.")
    validate_nonce(document.get("nonce"))
    return document


def encode_packet(document):
    try:
        packet = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (UnicodeError, TypeError, ValueError) as exc:
        raise ProtocolError("Unable to encode discovery packet.") from exc
    if len(packet) > MAX_PACKET:
        raise ProtocolError("Discovery packet exceeds size bounds.")
    return packet


def request_packet(nonce):
    return encode_packet({
        "protocol": MAGIC, "version": 1, "type": "query",
        "nonce": validate_nonce(nonce),
    })


def parse_request(packet):
    document = decode_packet(packet)
    if set(document) != {"protocol", "version", "type", "nonce"} or document["type"] != "query":
        raise ProtocolError("Invalid discovery request fields.")
    return document["nonce"]


def validate_name(name):
    if (
        not isinstance(name, str) or not name.strip() or len(name) > 64
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise ProtocolError("Receiver name must be 1-64 characters without control characters.")
    return name


def response_packet(nonce, name, address):
    return encode_packet({
        "protocol": MAGIC, "version": 1, "type": "receiver",
        "nonce": validate_nonce(nonce), "name": validate_name(name),
        "address": unicast_address(address), "app_version": APP_VERSION,
        "audio_port": 6005, "capabilities": [CAPABILITY],
    })


@dataclass(frozen=True)
class Receiver:
    name: str
    address: str
    app_version: str
    audio_port: int
    compatible: bool


def parse_response(packet, nonce, source_address):
    document = decode_packet(packet)
    expected = {
        "protocol", "version", "type", "nonce", "name", "address",
        "app_version", "audio_port", "capabilities",
    }
    if set(document) != expected or document["type"] != "receiver":
        raise ProtocolError("Invalid discovery response fields.")
    if document["nonce"] != nonce:
        raise ProtocolError("Stale or unsolicited discovery response.")
    address = unicast_address(document["address"])
    if address != unicast_address(source_address):
        raise ProtocolError("Advertised address does not match packet source.")
    name = validate_name(document["name"])
    version = document["app_version"]
    if (
        not isinstance(version, str) or not 1 <= len(version) <= 32
        or any(ord(character) < 33 or ord(character) > 126 for character in version)
    ):
        raise ProtocolError("Invalid application version.")
    port = document["audio_port"]
    if type(port) is not int or not 1 <= port <= 65535:
        raise ProtocolError("Invalid audio port.")
    capabilities = document["capabilities"]
    if (
        not isinstance(capabilities, list) or len(capabilities) > 8
        or any(
            not isinstance(item, str) or not 1 <= len(item) <= 64
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in item)
            for item in capabilities
        )
    ):
        raise ProtocolError("Invalid capabilities.")
    return Receiver(name, address, version, port, CAPABILITY in capabilities and port == 6005)


def serve(sock, name, stop, duration=30, ready=None):
    validate_name(name)
    deadline = time.monotonic() + duration
    recent = deque()
    rejected = 0
    sent = 0
    sock.settimeout(0.1)
    if ready is not None:
        ready.set()
    while not stop.is_set() and time.monotonic() < deadline:
        try:
            packet, peer = sock.recvfrom(MAX_PACKET + 1)
        except socket.timeout:
            continue
        except OSError as exc:
            if getattr(exc, "winerror", None) == 10040:
                rejected += 1
                continue
            raise
        now = time.monotonic()
        while recent and recent[0] <= now - 1:
            recent.popleft()
        if len(recent) >= 32:
            rejected += 1
            continue
        recent.append(now)
        try:
            nonce = parse_request(packet)
            unicast_address(peer[0])
        except ProtocolError:
            rejected += 1
            continue
        address = sock.getsockname()[0]
        if address == "0.0.0.0":
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
                route.connect(peer)
                address = route.getsockname()[0]
        sock.sendto(response_packet(nonce, name, address), peer)
        sent += 1
    logging.info("Discovery responder finished: responses=%s; rejected=%s", sent, rejected)


def discover(interfaces, port=PORT, timeout=2, cancel=None, unicast=False):
    if not 0 < timeout <= 5 or not math.isfinite(timeout):
        raise ValueError("Discovery timeout must be greater than zero and at most five seconds.")
    if not 1 <= len(interfaces) <= 8:
        raise ValueError("Select between one and eight IPv4 interfaces.")
    if cancel is not None and cancel.is_set():
        logging.info("Discovery cancelled before sending probes")
        return []
    nonce = secrets.token_hex(16)
    query = request_packet(nonce)
    sockets = []
    results = {}
    received = 0
    rejected = 0
    try:
        for value in interfaces:
            interface = ipaddress.IPv4Interface(value)
            address = unicast_address(str(interface.ip))
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sockets.append(sock)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.bind((address, 0))
            destination = address if unicast else str(interface.network.broadcast_address)
            sock.sendto(query, (destination, port))
        deadline = time.monotonic() + timeout
        while received < MAX_RECEIVED and len(results) < MAX_RESULTS:
            if cancel is not None and cancel.is_set():
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            readable, _, _ = select.select(sockets, [], [], min(0.1, remaining))
            for sock in readable:
                if received >= MAX_RECEIVED:
                    break
                received += 1
                try:
                    packet, source = sock.recvfrom(MAX_PACKET + 1)
                except OSError as exc:
                    if getattr(exc, "winerror", None) == 10040:
                        rejected += 1
                        continue
                    raise
                try:
                    if source[1] != port:
                        raise ProtocolError("Unexpected discovery response port.")
                    receiver = parse_response(packet, nonce, source[0])
                except ProtocolError:
                    rejected += 1
                    continue
                results.setdefault((receiver.address, receiver.audio_port), receiver)
                if received >= MAX_RECEIVED or len(results) >= MAX_RESULTS:
                    break
        logging.info(
            "Discovery finished: receivers=%s; packets=%s; rejected=%s; cancelled=%s",
            len(results), received, rejected, cancel is not None and cancel.is_set(),
        )
        return sorted(results.values(), key=lambda item: (item.name.casefold(), item.address))
    finally:
        for sock in sockets:
            sock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    responder = commands.add_parser("respond")
    responder.add_argument("--bind", required=True, help="Local IPv4, or 0.0.0.0 for broadcast")
    responder.add_argument("--name", default="Discovery Test Receiver")
    responder.add_argument("--duration", type=int, default=30, choices=range(1, 61))
    client = commands.add_parser("discover")
    client.add_argument("--interface", action="append", required=True, help="Local IPv4/prefix")
    client.add_argument("--unicast", action="store_true", help="Probe selected local IPs, not LAN broadcast")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "respond":
            bind = str(ipaddress.IPv4Address(args.bind))
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                sock.bind((bind, PORT))
                logging.info("Discovery prototype listening on UDP %s:%s", bind, PORT)
                serve(sock, args.name, threading.Event(), args.duration)
        else:
            for receiver in discover(args.interface, unicast=args.unicast):
                print(json.dumps(receiver.__dict__, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        logging.error("Discovery prototype failed: %s", exc)
        return 1
    except KeyboardInterrupt:
        logging.info("Discovery prototype cancelled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
