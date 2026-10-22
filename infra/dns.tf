locals {
  web_hostnames = {
    lims   = "lims.${var.cloudflare_zone_name}"
    argocd = "argocd.${var.cloudflare_zone_name}"
  }
}

module "tunnel" {
  source = "./modules/tunnel"

  account_id = module.dns.account_id
  name       = "medilab"
  origin     = "http://traefik.kube-system.svc.cluster.local:80"
  hostnames  = toset(values(local.web_hostnames))
}

module "dns" {
  source = "./modules/dns"

  zone_name = var.cloudflare_zone_name

  records = {
    for key, hostname in local.web_hostnames : key => {
      name    = hostname
      type    = "CNAME"
      content = module.tunnel.cname_target
      proxied = true
    }
  }
}

module "argocd_access" {
  source = "./modules/access"

  account_id = module.dns.account_id
  name       = "argocd"
  hostname   = local.web_hostnames.argocd
}
