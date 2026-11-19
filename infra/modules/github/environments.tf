data "github_user" "reviewer" {
  for_each = toset(flatten([for environment in values(var.environments) : environment.reviewers]))

  username = each.key
}

resource "github_repository_environment" "this" {
  for_each = var.environments

  repository          = var.repository_name
  environment         = each.key
  can_admins_bypass   = false
  prevent_self_review = false

  dynamic "reviewers" {
    for_each = length(each.value.reviewers) > 0 ? [each.value.reviewers] : []

    content {
      users = [for username in reviewers.value : data.github_user.reviewer[username].id]
    }
  }

  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }
}

resource "github_repository_environment_deployment_policy" "this" {
  for_each = var.environments

  repository     = var.repository_name
  environment    = github_repository_environment.this[each.key].environment
  branch_pattern = each.value.branch
  tag_pattern    = each.value.tag
}

resource "github_actions_environment_secret" "this" {
  for_each = {
    for pair in flatten([
      for environment, settings in var.environments : [
        for name in settings.secrets : { environment = environment, name = name }
        if contains(nonsensitive(keys(var.environment_secrets)), name)
      ]
    ]) : "${pair.environment}/${pair.name}" => pair
  }

  repository  = var.repository_name
  environment = github_repository_environment.this[each.value.environment].environment
  secret_name = each.value.name
  value       = var.environment_secrets[each.value.name]
}
