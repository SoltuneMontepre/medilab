variable "zone_name" {
  description = "The Cloudflare zone to create records in"
  type        = string
}

variable "records" {
  description = "DNS records to create, keyed by a label that is unique in the map"
  type = map(object({
    name    = string
    type    = string
    content = string
    ttl     = optional(number, 1)
    proxied = optional(bool, false)
  }))
  default = {}
}
