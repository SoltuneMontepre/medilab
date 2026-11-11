variable "account_id" {
  description = "The ID of the Cloudflare account that owns the tunnel"
  type        = string
}

variable "name" {
  description = "The name of the tunnel"
  type        = string
}

variable "origin" {
  description = "The address every public host name sends its requests to"
  type        = string
}

variable "hostnames" {
  description = "The public host names the tunnel serves"
  type        = set(string)
}
