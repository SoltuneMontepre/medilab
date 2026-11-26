output "account_id" {
  description = "The ID of the Cloudflare account that owns the zone"
  value       = data.cloudflare_zone.this.account.id
}

output "zone_id" {
  description = "The ID of the zone"
  value       = data.cloudflare_zone.this.id
}

output "record_fqdns" {
  description = "The name of each record, keyed like var.records"
  value       = { for key, record in cloudflare_dns_record.this : key => record.name }
}
