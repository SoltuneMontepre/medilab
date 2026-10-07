provider "doppler" {}

provider "github" {
  token = module.secrets.github_token
  owner = var.github_owner
}
