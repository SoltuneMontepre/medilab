# Moving a node

How a node of the production cluster in [Architecture](../infrastructure/architecture.md) moves to another machine, such as the witness leaving Azure, without stopping the system. The new node joins first and the old one leaves after, so the cluster never drops below three nodes.

## Requirements

- A Linux machine with a public IP, reachable by the other nodes on:

| Port       | Protocol | Use                     |
| ---------- | -------- | ----------------------- |
| 6443       | TCP      | Kubernetes API          |
| 2379, 2380 | TCP      | etcd                    |
| 10250      | TCP      | kubelet                 |
| 51820      | UDP      | WireGuard between nodes |
| 8883       | TCP      | MQTT, data sites only   |

- A data site needs at least the size of Server B: 2 cores, 4 GiB of memory and 40 GB of disk. A witness needs 2 cores and 2 GiB, the minimum of a k3s server with embedded etcd.
- `kubectl` with the `cnpg` plugin, connected to the cluster.

## Steps

1. **Read the join token** on any current node: `sudo cat /var/lib/rancher/k3s/server/token`.
2. **Join the new machine** as a k3s server, with the flags every node shares:

   ```bash
   curl -sfL https://get.k3s.io | K3S_TOKEN=<token> sh -s - server \
     --server https://<current node IP>:6443 \
     --node-external-ip <new node IP> \
     --flannel-backend=wireguard-native \
     --kube-apiserver-arg=default-unreachable-toleration-seconds=20 \
     --kube-apiserver-arg=default-not-ready-toleration-seconds=20 \
     --kube-controller-manager-arg=node-monitor-grace-period=20s \
     <role flags>
   ```

   | Role      | Role flags                                                     |
   | --------- | -------------------------------------------------------------- |
   | Witness   | `--node-taint node-role.kubernetes.io/witness=true:NoSchedule` |
   | Data site | `--node-label medilab/site=<a or b>`, the site it replaces     |

3. **Check the join:** `kubectl get nodes` lists the new node as `Ready`.
4. **For a data site, move its database instance:**
   1. `kubectl cordon <old node>`.
   2. If `kubectl cnpg status <cluster>` shows the primary on the old node, run `kubectl cnpg promote <cluster> <instance on the other site>`.
   3. `kubectl cnpg destroy <cluster> <instance on the old node>`. CloudNativePG creates a new instance on the new node and copies the data from the primary.
   4. Wait until `kubectl cnpg status <cluster>` shows two healthy instances.
5. **Remove the old node:** `kubectl drain <old node> --ignore-daemonsets --delete-emptydir-data`, then `kubectl delete node <old node>`. Deleting the node removes its etcd member.
6. **Shut down the old machine:**
   - Azure witness: `doppler run -- terraform -chdir=infra destroy -target=module.witness`.
   - Any other machine: run `/usr/local/bin/k3s-uninstall.sh` on it, then release it.
7. **For a data site, update DNS:** set the new public IP in the Terraform variables and run `task tf:apply`, so `mqtt.soltunemontepre.tech` points at it.

## Related documents

- [Architecture](../infrastructure/architecture.md)
- [Secrets](../infrastructure/secrets.md)
