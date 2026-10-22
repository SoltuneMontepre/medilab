output "client_id" {
  description = "The client ID of the service token, sent as CF-Access-Client-Id"
  value       = cloudflare_zero_trust_access_service_token.this.client_id
  sensitive   = true
}

output "client_secret" {
  description = "The client secret of the service token, sent as CF-Access-Client-Secret"
  value       = cloudflare_zero_trust_access_service_token.this.client_secret
  sensitive   = true
}
