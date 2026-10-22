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

    CF_ACCESS_CLIENT_ID     = module.argocd_access.client_id
    CF_ACCESS_CLIENT_SECRET = module.argocd_access.client_secret
  }

  variables = {
    ARGOCD_SERVER = local.web_hostnames.argocd
  }

  environments = {
    ansible = {
      branch = "main"
    }
    ansible-apply = {
      branch    = "main"
      reviewers = var.ansible_apply_reviewers
    }
  }

  environment_secrets = {
    DOPPLER_INFRA_TOKEN = module.secrets.doppler_infra_token
  }
}
