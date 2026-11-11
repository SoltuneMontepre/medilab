argo() {
  argocd "$@" \
    --server "$ARGOCD_SERVER" \
    --auth-token "$ARGOCD_AUTH_TOKEN" \
    --grpc-web
  return
}
