#!/bin/bash
set -euo pipefail
validation_dir=$(mktemp -d)
trap 'rm -rf "$validation_dir"' EXIT
validation_python=${ONLYOFFICE_VALIDATION_PYTHON:-python3}
curl --fail --silent --show-error --proto =https --proto-redir =https --location \
  https://github.com/yannh/kubeconform/releases/download/v0.7.0/kubeconform-linux-amd64.tar.gz \
  -o "$validation_dir/kubeconform.tgz"
printf '%s  %s\n' c31518ddd122663b3f3aa874cfe8178cb0988de944f29c74a0b9260920d115d3 "$validation_dir/kubeconform.tgz" | sha256sum -c -
tar -xzf "$validation_dir/kubeconform.tgz" -C "$validation_dir" kubeconform
curl --fail --silent --show-error --proto =https --proto-redir =https --location \
  https://github.com/cert-manager/cert-manager/releases/download/v1.21.2/cert-manager.crds.yaml \
  -o "$validation_dir/cert-manager.yaml"
curl --fail --silent --show-error \
  https://raw.githubusercontent.com/external-secrets/external-secrets/v2.13.0/deploy/crds/bundle.yaml \
  -o "$validation_dir/external-secrets.yaml"
curl --fail --silent --show-error \
  https://raw.githubusercontent.com/traefik/traefik/v3.7.13/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml \
  -o "$validation_dir/traefik.yaml"
curl --fail --silent --show-error \
  https://raw.githubusercontent.com/argoproj/argo-cd/v3.4.1/manifests/crds/application-crd.yaml \
  -o "$validation_dir/argocd.yaml"
printf '%s  %s\n' \
  262fef78478492cd35b73a1b227106b7802f9c056361d1f561d04b32d751337f "$validation_dir/cert-manager.yaml" \
  d4da9492a6906a3834bb1f5b7367575a29b5c43411017babc7a30728f465d1ba "$validation_dir/external-secrets.yaml" \
  1d5e8558803804562238b0d4a57174aadd6d87c36e3c4c55199ebcc356a9406c "$validation_dir/traefik.yaml" \
  fa8a0c7f8127f85bbbf57467e7c659ec7d47e7d162cc76c1b07482ebf2b98f49 "$validation_dir/argocd.yaml" | sha256sum -c -
for component in onlyoffice onlyoffice-integration onlyoffice-edge onlyoffice-monitor; do
  kubectl kustomize "infra/cluster/$component" > "$validation_dir/$component.yaml"
done
mkdir "$validation_dir/schema-cache"
# Core resources use Kubernetes schemas. Custom resources are checked below; Backup is unchanged base Odoo scope.
"$validation_dir/kubeconform" -strict -summary -ignore-missing-schemas \
  -cache "$validation_dir/schema-cache" "$validation_dir"/onlyoffice*.yaml
"$validation_python" tools/infrastructure/onlyoffice/validate_crds.py --skip-kind Backup \
  --crd "$validation_dir/cert-manager.yaml" --crd "$validation_dir/external-secrets.yaml" \
  --crd "$validation_dir/traefik.yaml" --crd "$validation_dir/argocd.yaml" \
  "$validation_dir"/onlyoffice*.yaml \
  infra/cluster/applications/onlyoffice.yaml infra/cluster/applications/onlyoffice-monitor.yaml \
  infra/cluster/onlyoffice-monitor/alerting-secret.yaml
