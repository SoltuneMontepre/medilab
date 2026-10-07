terraform {
  required_version = "1.15.8"

  cloud {
    organization = "soltunemontepre_devops"

    workspaces {
      name = "medilab"
    }
  }

  required_providers {
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
