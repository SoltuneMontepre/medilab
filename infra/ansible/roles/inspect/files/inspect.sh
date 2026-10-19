#!/usr/bin/env bash
# Prints a read-only report of a node: system, load, listening ports, containers, k3s, firewall and SSH.
# Runs on the node as root through the inspect role. Usage: inspect.sh "<k3s TCP ports>" "<k3s UDP ports>"

tcp_ports="$1"
udp_ports="$2"

section() {
  printf '\n== %s\n' "$1"
  return 0
}

has() {
  command -v "$1" >/dev/null 2>&1
  return $?
}

section "System"
printf 'Hostname: %s\n' "$(hostname)"
grep -E '^PRETTY_NAME=' /etc/os-release | cut -d= -f2 | tr -d '"'
printf 'Kernel: %s, %s\n' "$(uname -r)" "$(uname -m)"
printf 'CPUs: %s\n' "$(nproc)"
uptime

section "Memory"
free -h

section "Disk"
df -h -x tmpfs -x devtmpfs -x overlay -x squashfs

section "Top processes by CPU"
ps -eo pid,user,pcpu,pmem,etime,comm --sort=-pcpu | head -n 11

section "Top processes by memory"
ps -eo pid,user,pcpu,pmem,rss,comm --sort=-rss | head -n 11

section "Listening sockets"
ss -Htulpn

section "k3s ports in use"
busy=0
for port in $tcp_ports; do
  if ss -Htln "sport = :$port" | grep -q .; then
    printf 'TCP %s is in use\n' "$port"
    busy=1
  fi
done
for port in $udp_ports; do
  if ss -Huln "sport = :$port" | grep -q .; then
    printf 'UDP %s is in use\n' "$port"
    busy=1
  fi
done
if [[ "$busy" -eq 0 ]]; then
  printf 'None\n'
fi

section "Routes overlapping the k3s networks 10.42.0.0/16 and 10.43.0.0/16"
ip -4 route | grep -E '^10\.4[23]\.' || printf 'None\n'

section "Containers"
if has docker; then
  docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
else
  printf 'Docker not installed\n'
fi

section "Kubernetes"
if has k3s; then
  k3s --version | head -n 1
  systemctl is-active k3s || true
else
  printf 'k3s not installed\n'
fi
for unit in kubelet containerd microk8s.daemon-kubelite rke2-server; do
  if systemctl list-unit-files "$unit.service" >/dev/null 2>&1 && systemctl is-active --quiet "$unit"; then
    printf '%s is running\n' "$unit"
  fi
done

section "Firewall"
if has ufw; then
  ufw status
fi
if has nft; then
  printf 'nftables tables:\n'
  nft list tables
fi
printf 'nftables.service: %s\n' "$(systemctl is-enabled nftables 2>/dev/null || printf 'not installed')"
printf 'iptables INPUT policy: %s\n' "$(iptables -S INPUT 2>/dev/null | head -n 1)"

section "SSH"
sshd -T 2>/dev/null | grep -Ei '^(port|permitrootlogin|passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication) '

section "WireGuard"
if modinfo wireguard >/dev/null 2>&1; then
  printf 'Kernel module available\n'
else
  printf 'Kernel module missing\n'
fi

section "Failed units"
systemctl --failed --no-legend || true
