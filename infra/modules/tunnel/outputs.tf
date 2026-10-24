output "cname_target" {
  description = "The address a proxied CNAME record points a host name at"
  value       = "${cloudflare_zero_trust_tunnel_cloudflared.this.id}.cfargotunnel.com"
}

output "token" {
  description = "The token cloudflared connects with"
  value       = data.cloudflare_zero_trust_tunnel_cloudflared_token.this.token
  sensitive   = true
}
