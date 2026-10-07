provider "doppler" {
  doppler_token = var.doppler_token
}

provider "github" {
  token = module.secrets.github_token
  owner = var.github_owner
}
