variable "account_id" {
  description = "The ID of the Cloudflare account that owns the bucket"
  type        = string
}

variable "name" {
  description = "The name of the bucket"
  type        = string
}

variable "location" {
  description = "The region hint the bucket is created in; R2 honours it only when the bucket is first created"
  type        = string
}

variable "domain" {
  description = "The public host name that serves the bucket's objects over HTTPS"
  type        = string
}

variable "zone_id" {
  description = "The ID of the Cloudflare zone that owns the domain"
  type        = string
}
