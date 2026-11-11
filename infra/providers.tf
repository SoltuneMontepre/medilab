provider "cloudflare" {
  api_token = module.secrets.cloudflare_api_token
}

provider "doppler" {}

provider "github" {
  token = module.secrets.github_token
  owner = var.github_owner
}
