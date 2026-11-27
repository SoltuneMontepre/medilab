output "tunnel_token" {
  description = "The token of the tunnel, stored in Doppler as CLOUDFLARE_TUNNEL_TOKEN"
  value       = module.tunnel.token
  sensitive   = true
}

output "release_bucket_public_address" {
  description = "The public address of the medilab-release bucket, stored in Doppler as RELEASE_BUCKET_PUBLIC_ADDRESS"
  value       = module.release_bucket.public_address
}
