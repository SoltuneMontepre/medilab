variable "repository_name" {
  description = "The repository name, without the owner, to publish Actions secrets to"
  type        = string
}

variable "secrets" {
  description = "GitHub Actions repository secrets to publish, as name => value"
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "variables" {
  description = "GitHub Actions repository variables to publish, as name => value"
  type        = map(string)
  default     = {}
}

variable "environments" {
  description = "Deployment environments to create, as name => the only branch that may deploy and the GitHub usernames that must approve"
  type = map(object({
    branch    = string
    reviewers = optional(list(string), [])
  }))
  default = {}
}

variable "environment_secrets" {
  description = "Secrets to publish to every environment, as name => value"
  type        = map(string)
  default     = {}
  sensitive   = true
}
