output "name" {
  description = "The name of the bucket"
  value       = cloudflare_r2_bucket.this.name
}

output "public_address" {
  description = "The HTTPS address the bucket's objects are downloaded from"
  value       = "https://${cloudflare_r2_custom_domain.this.domain}"
}
