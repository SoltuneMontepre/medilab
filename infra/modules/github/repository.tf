resource "github_repository_ruleset" "main" {
  repository  = var.repository_name
  name        = "main"
  target      = "branch"
  enforcement = "active"

  bypass_actors {
    actor_type  = "OrganizationAdmin"
    bypass_mode = "always"
  }

  bypass_actors {
    actor_id    = 15368
    actor_type  = "Integration"
    bypass_mode = "always"
  }

  conditions {
    ref_name {
      include = ["~DEFAULT_BRANCH"]
      exclude = []
    }
  }

  rules {
    deletion                = true
    required_linear_history = true

    pull_request {
      allowed_merge_methods             = ["squash", "rebase"]
      required_approving_review_count   = 1
      required_review_thread_resolution = true
    }

    required_status_checks {
      strict_required_status_checks_policy = true

      dynamic "required_check" {
        for_each = var.required_checks

        content {
          context        = required_check.key
          integration_id = required_check.value
        }
      }
    }
  }
}

resource "github_workflow_repository_permissions" "this" {
  repository                       = var.repository_name
  default_workflow_permissions     = "read"
  can_approve_pull_request_reviews = true
}
