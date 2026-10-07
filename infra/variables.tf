variable "doppler_token" {
  description = "Doppler token that can read the tf config"
  type        = string
  sensitive   = true
}

variable "doppler_project" {
  description = "The Doppler project holding the secrets Terraform publishes"
  type        = string
  default     = "medilab"
}

variable "doppler_config" {
  description = "The Doppler config Terraform reads its secrets from"
  type        = string
  default     = "tf"
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
