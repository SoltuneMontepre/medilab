module "secrets" {
  source = "./modules/secrets"

  doppler_project = var.doppler_project
  doppler_config  = var.doppler_config
}

module "github_actions" {
  source = "./modules/github"

  repository_name = var.github_repository

  secrets = {
    SONAR_TOKEN   = module.secrets.sonar_token
    DOPPLER_TOKEN = module.secrets.doppler_token
    TF_API_TOKEN  = module.secrets.tf_api_token
  }
}
