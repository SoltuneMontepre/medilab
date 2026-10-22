resource "cloudflare_zero_trust_access_service_token" "this" {
  account_id = var.account_id
  name       = var.name
}

resource "cloudflare_zero_trust_access_policy" "this" {
  account_id = var.account_id
  name       = "${var.name} service token"
  decision   = "non_identity"

  include = [{
    service_token = {
      token_id = cloudflare_zero_trust_access_service_token.this.id
    }
  }]
}

resource "cloudflare_zero_trust_access_application" "this" {
  account_id = var.account_id
  name       = var.name
  type       = "self_hosted"
  domain     = var.hostname

  policies = [{
    id         = cloudflare_zero_trust_access_policy.this.id
    precedence = 1
  }]
}
