output "github_token" {
  description = "GitHub token that publishes the Actions secrets"
  value       = data.doppler_secrets.this.map["GITHUB_TOKEN"]
  sensitive   = true
}

output "sonar_token" {
  description = "SonarQube analysis token published as the SONAR_TOKEN Actions secret"
  value       = data.doppler_secrets.this.map["SONARQUBE_TOKEN"]
  sensitive   = true
}

output "doppler_token" {
  description = "Doppler token the pipelines read secrets with, published as the DOPPLER_TOKEN Actions secret"
  value       = data.doppler_secrets.this.map["DOPPLER_TOKEN"]
  sensitive   = true
}

output "tf_api_token" {
  description = "HCP Terraform team token published as the TF_API_TOKEN Actions secret"
  value       = data.doppler_secrets.this.map["TERRAFORM_TOKEN"]
  sensitive   = true
}

output "doppler_infra_token" {
  description = "Doppler token that reads the infra config, published as the DOPPLER_INFRA_TOKEN secret of the Ansible environments"
  value       = data.doppler_secrets.this.map["DOPPLER_INFRA_TOKEN"]
  sensitive   = true
}

output "cloudflare_api_token" {
  description = "Cloudflare token that edits DNS and the tunnel of the zone"
  value       = data.doppler_secrets.this.map["CLOUDFLARE_API_TOKEN"]
  sensitive   = true
}

output "argocd_auth_token" {
  description = "Token of the Argo CD release account, published as the ARGOCD_AUTH_TOKEN Actions secret"
  value       = data.doppler_secrets.this.map["ARGOCD_AUTH_TOKEN"]
  sensitive   = true
}
