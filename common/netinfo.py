"""Informazioni di rete per la schermata di avvio.

Tutto con fallback: se un comando manca o fallisce si restituisce None,
perche' lo splash deve comparire comunque.
"""
import socket
import subprocess


def _run(cmd, timeout=4):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if out.returncode == 0:
            return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def ip_address():
    """IP della rotta predefinita. Non apre connessioni: UDP non fa handshake."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))   # rete TEST-NET-1, non raggiungibile
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def ssid():
    name = _run(["iwgetid", "-r"])
    if name:
        return name
    out = _run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"])
    if out:
        for line in out.splitlines():
            if line.startswith("yes:"):
                return line.split(":", 1)[1] or None
    return None


def mdns_name():
    host = socket.gethostname()
    return f"{host}.local" if host else None


def time_synced():
    out = _run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"])
    if out is None:
        return None
    return out.strip() == "yes"


def snapshot():
    return {
        "ip": ip_address(),
        "ssid": ssid(),
        "mdns": mdns_name(),
        "ntp": time_synced(),
    }
