output "tunnel_token" {
  description = "The token of the tunnel, stored in Doppler as CLOUDFLARE_TUNNEL_TOKEN"
  value       = module.tunnel.token
  sensitive   = true
}
