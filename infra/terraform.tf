terraform {
  required_version = "1.15.8"

  cloud {
    organization = "soltunemontepre_devops"

    workspaces {
      name = "medilab"
    }
  }

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "5.28.1"
    }

    doppler = {
      source  = "DopplerHQ/doppler"
      version = "1.21.4"
    }

    github = {
      source  = "integrations/github"
      version = "6.13.0"
    }
  }
}
