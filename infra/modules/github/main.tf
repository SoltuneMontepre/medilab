resource "github_actions_secret" "this" {
  for_each = nonsensitive(toset(keys(var.secrets)))

  repository  = var.repository_name
  secret_name = each.key
  value       = var.secrets[each.key]
}
