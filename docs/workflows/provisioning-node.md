# Provisioning a node

How a machine gets ready for MediLab: give Ansible access, check the connection, look at what already runs, preview the changes, then apply them. Everything happens in the VPS web console, the Doppler dashboard and the GitHub Actions page; no secret passes through a personal computer. What Ansible installs is described in [Provisioning](../infrastructure/provisioning.md).

## Requirements

- Root access to the node through the VPS web console.
- Write access to the `medilab` `infra` config in the Doppler dashboard.
- Permission to run the `cd-ansible` workflow; `apply` also needs a reviewer of the `ansible-apply` environment. See [Pipelines](../infrastructure/pipelines.md#cd-ansible).
- `DOPPLER_INFRA_TOKEN` published to the Ansible environments; see [Secrets](../infrastructure/secrets.md).

## Steps

1. **Create the Ansible key**, as root in the node's console, only on the first node of the cluster. Every node trusts the same key:

   ```bash
   ssh-keygen -t ed25519 -N "" -C medilab-ansible -f /root/medilab_ansible
   ```

   On a later node, copy the line in `/home/ansible/.ssh/authorized_keys` of a current node instead, and write it to `/root/medilab_ansible.pub`.

2. **Create the `ansible` user**, as root in the console. It changes no other user, service or setting:

   ```bash
   useradd --create-home --shell /bin/bash ansible
   install -d -m 700 -o ansible -g ansible /home/ansible/.ssh
   cat /root/medilab_ansible.pub > /home/ansible/.ssh/authorized_keys
   chown ansible:ansible /home/ansible/.ssh/authorized_keys
   chmod 600 /home/ansible/.ssh/authorized_keys
   printf 'ansible ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/90-ansible
   chmod 440 /etc/sudoers.d/90-ansible
   visudo -cf /etc/sudoers.d/90-ansible
   ```

3. **Store the private key in Doppler**, on the first node only. Show it with `cat /root/medilab_ansible`, paste every line, from `-----BEGIN` to `-----END`, into the Doppler dashboard as `ANSIBLE_SSH_PRIVATE_KEY` in `infra`, then delete it from the node and clear the screen:

   ```bash
   shred -u /root/medilab_ansible && rm /root/medilab_ansible.pub && clear
   ```

4. **Create the cluster token**, on the first node only. Paste the output of this command into the Doppler dashboard as `K3S_TOKEN` in `infra`, then clear the screen:

   ```bash
   openssl rand -hex 32
   ```

   Set `K3S_TOKEN` once for the whole cluster; changing it later breaks joining nodes and snapshot restores.

5. **Store the node's address** in the Doppler dashboard as `NODE_<site>_PUBLIC_ADDRESS` in `infra`, such as `NODE_A_PUBLIC_ADDRESS`.
6. **Trust the node's host key.** Show it in the console with `cat /etc/ssh/ssh_host_ed25519_key.pub`, and add one line to `infra/ansible/known_hosts`: the node's public address, a space, then the line the command printed, such as `203.0.113.10 ssh-ed25519 AAAA... root@host`. Ansible connects only to hosts whose key matches a line there.
7. **Add the node to the inventory** in `infra/ansible/inventories/production/`, unless it is there already: the host in `hosts.yml` with its `ansible_host`, and its `host_vars` file. Add its `NODE_*_PUBLIC_ADDRESS` variable to the `ansible` service in `tools/ansible/compose.yml`. Merge steps 6 and 7 into `main` through a pull request, since `cd-ansible` only runs from `main`.
8. **Check the connection:** run `cd-ansible` with `ping`, from the Actions page with **Run workflow** on `main`. Every node answers `pong`. A failure here is about SSH, the key or `sudo`; nothing has been changed. Set `limit` to the node's name to run on it alone.
9. **Inspect the node:** run `cd-ansible` with `inspect`. Read the report in the run's log before going on:
   - The k3s ports and networks it lists as in use must be freed or moved first.
   - The memory and CPU that other programs use sets `k3s_system_reserved` in the node's `host_vars`, so pods leave them enough.
   - A k3s or other Kubernetes that is already running is not changed by Ansible; decide with the owner what happens to it first.
10. **Preview the changes:** run `cd-ansible` with `check`. It runs every check and shows each file and setting that would change, without changing it.
11. **Apply:** run `cd-ansible` with `apply`. The run waits until a reviewer approves it on its page. Running it again shows no changes.
12. **Read the kubeconfig** when you need the cluster's API: `cat /etc/rancher/k3s/k3s.yaml` as root in the console. Someone with Docker and Doppler access can fetch it with `task ansible:kubeconfig` instead. Never print it in an Actions log.

Once, on the first node, Argo CD starts deploying `infra/cluster/`:

13. **Store the cluster's secrets** in the Doppler dashboard, in `infra`:
    - `CLUSTER_DOPPLER_TOKEN`: a service token of `infra` with read access, valid for a year, created under the config's **Access** tab.
    - `ODOO_ADMIN_PASSWORD`: the output of `openssl rand -hex 32` in the console, which you clear afterwards.
    - `CLOUDFLARE_TUNNEL_TOKEN`: the token of the tunnel, from the Cloudflare dashboard.
14. **Turn on the root application:** set `argocd_root_application_enabled: true` in `infra/ansible/inventories/production/group_vars/k3s_servers.yml` through a pull request, then run `cd-ansible` with `check` and `apply`. Argo CD syncs the applications in [Cluster](../infrastructure/cluster.md) wave by wave.

To renew `CLUSTER_DOPPLER_TOKEN` before it expires, create a new service token, replace the secret in Doppler, then run `cd-ansible` with `apply`.

## Related documents

- [Provisioning](../infrastructure/provisioning.md)
- [Cluster](../infrastructure/cluster.md)
- [Pipelines](../infrastructure/pipelines.md)
- [Moving a node](moving-node.md)
- [Secrets](../infrastructure/secrets.md)
