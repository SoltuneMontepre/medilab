variable "account_id" {
  description = "The ID of the Cloudflare account that owns the application"
  type        = string
}

variable "name" {
  description = "The name of the application, its policy and its service token"
  type        = string
}

variable "hostname" {
  description = "The host name the application guards"
  type        = string
}
