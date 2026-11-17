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
  description = "Deployment environments to create, as name => the only branch or tag pattern that may deploy, the GitHub usernames that must approve and the names of the environment_secrets it gets"
  type = map(object({
    branch    = optional(string)
    tag       = optional(string)
    reviewers = optional(list(string), [])
    secrets   = optional(list(string), [])
  }))
  default = {}

  validation {
    condition     = alltrue([for environment in values(var.environments) : (environment.branch == null) != (environment.tag == null)])
    error_message = "Each environment names either a branch or a tag pattern."
  }
}

variable "environment_secrets" {
  description = "Secrets the environments get, as name => value; an environment gets those it names that are present"
  type        = map(string)
  default     = {}
  sensitive   = true
}

variable "required_checks" {
  description = "The status checks the default branch requires, as check name => the ID of the GitHub App that reports it"
  type        = map(number)
}

variable "release_app_id" {
  description = "ID of the GitHub App that may push to the default branch without a pull request"
  type        = number
}
