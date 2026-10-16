# Architecture

How MediLab runs in production: two servers in two locations, each holding the database, so that losing either location keeps the system online.

## Overview

```mermaid
flowchart LR
    user[Users and client apps] --> cf[Cloudflare]
    device[IoT devices] -- MQTT over TLS --> mqttA
    device -- MQTT over TLS --> mqttB
    cf -- tunnel --> cfa
    cf -- tunnel --> cfb

    subgraph siteA[Site A]
        cfa[cloudflared] --> traefikA[Traefik] --> odooA[Odoo]
        mqttA[EMQX]
        pgA[(Postgres primary)]
    end

    subgraph siteB[Site B]
        cfb[cloudflared] --> traefikB[Traefik] --> odooB[Odoo]
        mqttB[EMQX]
        pgB[(Postgres replica)]
    end

    subgraph siteC[Site C: Azure]
        witness[Witness node]
    end

    odooA --> rw{{postgres rw service}}
    odooB --> rw
    rw --> pgA
    pgA -- streaming replication --> pgB
    odooA --> filestore[(filestore bucket)]
    odooB --> filestore
    pgA -- WAL archive and base backups --> backups[(backups bucket)]
```

## Nodes

| Node     | Location | Host                                                   | Runs                                      |
| -------- | -------- | ------------------------------------------------------ | ----------------------------------------- |
| Server A | Site A   | VPS SSD LINUX 8 `soltune-xoha`                         | Workloads and a database instance         |
| Server B | Site B   | VPS SSD LINUX 2 `soltune-xxex`: 2 cores, 4 GiB, 40 GB  | Workloads and a database instance         |
| Witness  | Site C   | Azure VM in Southeast Asia, Azure for Students account | Cluster quorum only; tainted `NoSchedule` |

- The three nodes form one k3s cluster, each a k3s server with embedded etcd.
- Every decision to promote a site needs a majority of three votes. With the witness in a third location, losing either data site leaves two of three votes, so the surviving site takes over. Two nodes alone cannot form a majority after a loss.
- Nodes reach each other over WireGuard (`--flannel-backend=wireguard-native`).
- Any Linux machine with a public IP can take a node's place; [Moving a node](../workflows/moving-node.md) replaces one without stopping the system.
- The two VPSes are rented and installed by hand; Terraform does not create them. Their public IPs are Terraform variables, used for the MQTT DNS records.

## Witness

- The witness is an Azure VM in the Southeast Asia region, created by the `witness` module in `infra/` with the `azurerm` provider. Its region and VM size are variables of the module.
- It runs only k3s and WireGuard. Its disk holds a copy of etcd and no business data.
- Without a witness the cluster keeps serving, but a lost data site is not failed over: the surviving site alone holds no majority, so the Kubernetes API stops and the replica is not promoted. A new witness restores failover by joining the cluster.

## Deployment

- Argo CD runs in the cluster and syncs the manifests in `infra/cluster/` on `main`.
- `cd-core` publishes the release image and commits its SHA tag to `infra/cluster/`; Argo CD then rolls it out. Roll back by reverting that commit.
- A change to the cluster is a change to `infra/cluster/`, never a `kubectl` edit; Argo CD reverts edits made by hand.

## Database

- CloudNativePG runs one Postgres `Cluster` with two instances, one per data site, each on the local storage of its node.
- Odoo connects to the cluster's `-rw` service, which always points at the primary.
- Replication uses `dataDurability: preferred`: writes wait for both sites while both are up, and continue on one site while the other is down.
- **Switchover:** `kubectl cnpg promote <cluster> <instance>` moves the primary to the other site without losing data.
- **Failover:** when the primary's site is lost, the replica is promoted automatically. The last writes not yet replicated can be lost.
- A returning instance resynchronises and rejoins as a replica.

## Object storage

Two buckets, one per Object Storage Lite plan, with the same provider as the VPSes:

| Bucket      | Holds                                 |
| ----------- | ------------------------------------- |
| `filestore` | Odoo attachments                      |
| `backups`   | Postgres WAL archive and base backups |

## Backups

- CloudNativePG archives WAL continuously and takes a scheduled base backup to the `backups` bucket through the Barman Cloud plugin.
- The base backup schedule and the retention period are parameters in `infra/cluster/`, with defaults of daily at 02:00 and 30 days.
- A restore creates a new cluster from the bucket, to any point in time the archive covers.

## Ingress

- Web traffic comes in only through Cloudflare Tunnel. `cloudflared` runs two replicas of the same tunnel, one per data site, and connects outbound.
- Cloudflare routes requests to connected replicas, so a lost site stops receiving traffic.
- Web DNS records in the `soltunemontepre.tech` zone, such as `lims.soltunemontepre.tech`, are proxied CNAMEs to `<tunnel-id>.cfargotunnel.com`; Cloudflare terminates TLS and `cloudflared` reaches Traefik over plain HTTP.

## MQTT

- IoT devices, such as the SIM7600 environment monitors, publish over MQTT with TLS on port 8883, which Cloudflare Tunnel cannot carry.
- EMQX runs one replica per data site, clustered, each listening on its node's public IP.
- `mqtt.soltunemontepre.tech` is a DNS-only record with one A record per data site, so devices are spread across both sites. A device that loses its broker reconnects with backoff and resolves the name again.
- The broker presents a Cloudflare Origin CA certificate for `mqtt.soltunemontepre.tech`, created by Terraform.

## Odoo

- Two replicas, kept on different data sites by pod anti-affinity.
- Attachments are stored in object storage outside both servers, so either replica serves every file.
- Sessions are stored on each replica's local disk; users log in again after a failover.
- Module installs and upgrades run in a one-off Job per release, never at pod start.
- Scheduled actions run on both replicas; Odoo locks each job so it runs once.

## Failover timing

k3s waits five minutes by default before moving pods off an unreachable node. Every k3s server sets:

```text
--kube-apiserver-arg=default-unreachable-toleration-seconds=20
--kube-apiserver-arg=default-not-ready-toleration-seconds=20
--kube-controller-manager-arg=node-monitor-grace-period=20s
```

- CoreDNS, Traefik, `cloudflared` and EMQX run two replicas each, one per data site.
- The CloudNativePG operator tolerates the witness taint, so it keeps running when a data site is lost.
- A lost site recovers in about 30 to 60 seconds.

## Related documents

- [Moving a node](../workflows/moving-node.md)
- [Pipelines](pipelines.md)
- [Secrets](secrets.md)
- [Terraform conventions](../conventions/terraform.md)
