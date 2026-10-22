variable "doppler_project" {
  description = "The Doppler project holding the secrets Terraform publishes"
  type        = string
  default     = "medilab"
}

variable "doppler_config" {
  description = "The Doppler config Terraform reads its secrets from"
  type        = string
  default     = "dev"
}

variable "github_owner" {
  description = "The GitHub org or user that owns the repository"
  type        = string
  default     = "SoltuneMontepre"
}

variable "github_repository" {
  description = "The repository name, without the owner, that receives the Actions secrets"
  type        = string
  default     = "medilab"
}

variable "ansible_apply_reviewers" {
  description = "GitHub usernames that must approve every cd-ansible apply"
  type        = list(string)
  default     = ["hatohui"]
}

variable "cloudflare_zone_name" {
  description = "The Cloudflare zone that owns MediLab's host names"
  type        = string
  default     = "soltunemontepre.tech"
}

variable "release" {
  description = "How cd-core releases: mode is continuous or window, days such as Mon-Sun or Sat,Sun, and hours such as 23-5 in Asia/Ho_Chi_Minh"
  type = object({
    mode  = string
    days  = string
    hours = string
  })
  default = {
    mode  = "continuous"
    days  = "Mon-Sun"
    hours = "23-5"
  }

  validation {
    condition     = contains(["continuous", "window"], var.release.mode)
    error_message = "release.mode is continuous or window."
  }
}

variable "required_checks" {
  description = "The status checks main requires, as check name => the ID of the GitHub App that reports it"
  type        = map(number)
  default = {
    "build"                             = 15368
    "lint"                              = 15368
    "sonarqube"                         = 15368
    "test"                              = 15368
    "tools"                             = 15368
    "infrastructure"                    = 15368
    "GitGuardian Security Checks"       = 46505
    "Naming conventions / Branch"       = 17675
    "Naming conventions / Pull request" = 17675
  }
}
