# Provisioning

How the nodes in [Architecture](architecture.md) are set up: Ansible in `infra/ansible/` installs k3s and Argo CD on each machine, and Argo CD then deploys everything else from `infra/cluster/`, described in [Cluster](cluster.md).

## Rules

- A node may already run other programs. Provisioning changes only what MediLab needs and leaves the rest of the host as it is.
- Every step checks first and skips what is already in place. Running the playbook again changes nothing.
- A k3s or Argo CD that Ansible did not install is never changed: the run stops on that node, or skips Argo CD, and says so.
- Nothing is upgraded or removed by a normal run: packages are only installed when missing, and a different k3s version is reported, not replaced.
- Every run is checked first with `task ansible:check`, which shows the changes without making them.

## Playbooks

| Playbook               | Does                                                                                               |
| ---------------------- | -------------------------------------------------------------------------------------------------- |
| `inspect.yml`          | Reports the system, load, listening ports, containers, Kubernetes, firewall and SSH of every node. |
| `site.yml`             | Provisions every node with the roles below, one node at a time.                                    |
| `fetch_kubeconfig.yml` | Copies the cluster's admin kubeconfig to `infra/ansible/kubeconfig.yml`, which Git ignores.        |

## Roles

| Role            | Does                                                                                                                                                                                                                                                                                                                                        |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `preflight`     | Stops on an unsupported system, a missing WireGuard module or a k3s installed outside Ansible. Before a first install, also stops when memory, disk, the k3s ports or the k3s networks are already in use.                                                                                                                                  |
| `base`          | Installs missing packages and raises the inotify limits that are below what k3s needs. Never lowers a limit.                                                                                                                                                                                                                                |
| `ssh_hardening` | Turns off root and password login. Off by default, since other people may log in with a password; turn it on with `ssh_hardening_enabled`.                                                                                                                                                                                                  |
| `node_firewall` | Drops traffic to the k3s ports from anywhere but the nodes, the cluster networks and `node_firewall_admin_sources`, in its own nftables table, so the host's other rules are untouched.                                                                                                                                                     |
| `k3s`           | Installs the pinned k3s version as a server, configured from `/etc/rancher/k3s/config.yaml`, and waits until the node is ready.                                                                                                                                                                                                             |
| `argocd`        | Installs the pinned Argo CD chart through the k3s Helm controller, with health checks for applications and CloudNativePG backups. With `argocd_root_application_enabled`, stores `CLUSTER_DOPPLER_TOKEN` as the `doppler-token` Secret and adds the `medilab` application that syncs `infra/cluster/` on `main`; see [Cluster](cluster.md). |

## k3s

- Every node is a k3s server with embedded etcd. The first node starts the cluster (`k3s_cluster_init`); the others join it through `k3s_server_url`, so Server B and the witness are added without moving any data.
- The cluster token is `K3S_TOKEN` in Doppler, so every server and every restore of an etcd snapshot uses the same one.
- ServiceLB is turned off and Traefik's service is `ClusterIP`, so k3s takes no host port such as 80 or 443 from programs already on the node.
- `k3s_system_reserved` and `k3s_kube_reserved` keep CPU and memory for the rest of the host, so pods cannot starve it.
- Secrets are encrypted at rest in etcd.
- etcd is snapshotted every six hours and 28 snapshots are kept. When `k3s_etcd_s3_bucket` is set, the snapshots also go to that bucket under `k3s-etcd/`.
- The Kubernetes API listens on 6443 but only the nodes and the admin sources reach it. Developers use an SSH tunnel: `ssh -N -L 6443:127.0.0.1:6443 ansible@<node>`, then `kubectl --kubeconfig infra/ansible/kubeconfig.yml`.

## Running Ansible

GitHub Actions is the control node: the `cd-ansible` workflow runs the playbooks from `main`, by hand, with `ping`, `inspect`, `check` or `apply`; see [Pipelines](pipelines.md#cd-ansible). The SSH key exists only in Doppler.

Ansible runs in a container built from `tools/ansible/ansible.dockerfile`, the same in the workflow and on a developer machine. It is started through `doppler run` with the `infra` config, which passes the node addresses, the SSH key, the bucket keys and the cluster's Doppler token; see [Secrets](secrets.md). The SSH key is loaded into an agent inside the container and never written to disk.

- Node host keys are pinned in `infra/ansible/known_hosts`, one line per node: its public address, the key type and the key, copied from `/etc/ssh/ssh_host_ed25519_key.pub` in the VPS web console. Ansible refuses a node whose key is missing or different.
- GitHub-hosted runners have no fixed addresses, so SSH on port 22 accepts connections from anywhere and the `ansible` user logs in with its key only. Turn on `ssh_hardening_enabled` once the owner confirms that nobody logs in to the node with a password, so password and root login are refused for every user.

Anyone with Docker and read access to `infra` can run the same commands locally:

| Task                      | Does                                                                     |
| ------------------------- | ------------------------------------------------------------------------ |
| `task ansible:ping`       | Checks that Ansible reaches every node over SSH and can use `sudo`.      |
| `task ansible:inspect`    | Runs `inspect.yml`.                                                      |
| `task ansible:check`      | Runs `site.yml` in check mode with a diff; nothing changes on the nodes. |
| `task ansible:apply`      | Runs `site.yml`.                                                         |
| `task ansible:kubeconfig` | Runs `fetch_kubeconfig.yml`.                                             |
| `task ansible:lint`       | Runs `ansible-lint` with the `production` profile.                       |

Arguments after `--` go to Ansible, such as `task ansible:check -- --limit soltune-xoha`.

## Versions

Every version is pinned and upgraded by changing it in the code:

| What                       | Where                                                |
| -------------------------- | ---------------------------------------------------- |
| k3s                        | `k3s_version` in the `k3s` role                      |
| Argo CD chart              | `argocd_chart_version` in `argocd` role              |
| ansible-core               | `tools/ansible/ansible.dockerfile`               |
| Collections                | `infra/ansible/requirements.yml`                     |
| Everything Argo CD deploys | `infra/cluster/`; see [Cluster](cluster.md#versions) |

A running k3s is only upgraded with `task ansible:apply -- -e k3s_upgrade=true`.

## Related documents

- [Provisioning a node](../workflows/provisioning-node.md)
- [Architecture](architecture.md)
- [Cluster](cluster.md)
- [Moving a node](../workflows/moving-node.md)
- [Secrets](secrets.md)
