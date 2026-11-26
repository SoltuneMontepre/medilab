module "release_bucket" {
  source = "./modules/r2_bucket"

  account_id = module.dns.account_id
  zone_id    = module.dns.zone_id
  name       = "medilab-release"
  location   = "apac"
  domain     = "release.${var.cloudflare_zone_name}"
}
