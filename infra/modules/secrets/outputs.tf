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
