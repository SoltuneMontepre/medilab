resource "cloudflare_r2_bucket" "this" {
  account_id    = var.account_id
  name          = var.name
  location      = var.location
  storage_class = "Standard"
}

resource "cloudflare_r2_custom_domain" "this" {
  account_id  = var.account_id
  bucket_name = cloudflare_r2_bucket.this.name
  domain      = var.domain
  zone_id     = var.zone_id
  enabled     = true
  min_tls     = "1.2"
}
