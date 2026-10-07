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
