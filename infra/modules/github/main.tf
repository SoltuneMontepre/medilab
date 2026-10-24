resource "github_actions_secret" "this" {
  for_each = nonsensitive(toset(keys(var.secrets)))

  repository  = var.repository_name
  secret_name = each.key
  value       = var.secrets[each.key]
}

resource "github_actions_variable" "this" {
  for_each = var.variables

  repository    = var.repository_name
  variable_name = each.key
  value         = each.value
}
