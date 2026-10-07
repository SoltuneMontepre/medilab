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
