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

    ARGOCD_AUTH_TOKEN = module.secrets.argocd_auth_token

    RELEASE_APP_ID          = module.secrets.release_app_id
    RELEASE_APP_PRIVATE_KEY = module.secrets.release_app_private_key

    CF_ACCESS_CLIENT_ID     = module.argocd_access.client_id
    CF_ACCESS_CLIENT_SECRET = module.argocd_access.client_secret
  }

  variables = {
    ARGOCD_SERVER = local.web_hostnames.argocd
    RELEASE_MODE  = var.release.mode
    RELEASE_DAYS  = var.release.days
    RELEASE_HOURS = var.release.hours
  }

  required_checks = var.required_checks
  release_app_id  = tonumber(nonsensitive(module.secrets.release_app_id))

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

import {
  to = module.github_actions.github_repository_ruleset.main
  id = "${var.github_repository}:24628840"
}
