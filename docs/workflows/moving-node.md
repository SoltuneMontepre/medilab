# Moving a node

How a node of the production cluster in [Architecture](../infrastructure/architecture.md) moves to another machine, such as the witness leaving Azure, without stopping the system. The new node joins first and the old one leaves after, so the cluster never drops below three nodes. To add a node instead, such as Server B or the witness joining Server A, follow steps 1 to 3 only.

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

1. **Give Ansible access** to the new machine and add it to the inventory: steps 1, 2 and 5 to 7 of [Provisioning a node](provisioning-node.md). In its `host_vars`, set the role:

   | Role      | `host_vars`                                                          |
   | --------- | -------------------------------------------------------------------- |
   | Witness   | `k3s_node_taints: [node-role.kubernetes.io/witness=true:NoSchedule]` |
   | Data site | `k3s_node_labels: [medilab/site=<a or b>]`, the site it replaces     |

   When the old node is the one in `k3s_server_url`, point it at another current node. Only the node that started the cluster has `k3s_cluster_init`.

2. **Join the new machine:** run `cd-ansible` with `check`, then with `apply`. Every node is provisioned, so the firewalls of the current nodes also let the new one in, and the new machine joins as a k3s server with the cluster token from Doppler.
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
7. **Forget the old machine:** remove it from the inventory and its key from `infra/ansible/known_hosts`, then run `cd-ansible` with `apply`, so the firewalls no longer let it in.
8. **For a data site, update DNS:** set the new public IP in the Terraform variables and run `task tf:apply`, so `mqtt.soltunemontepre.tech` points at it.

## Related documents

- [Architecture](../infrastructure/architecture.md)
- [Provisioning a node](provisioning-node.md)
- [Secrets](../infrastructure/secrets.md)
