---
# Copied from https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/syntax-for-issue-forms
name: Bug Report
description: File a bug report.
title: "[Bug]: "
labels: ["kind:feature", "needs-triage"]
assignees:
  - octocat
type: bug
body:
  - type: markdown
    attributes:
      value: |
        Thanks for taking the time to fill out a feature request.
  - type: textarea
    attributes:
      label: Feature description
      description: A short description of the feature you would like added to beetkeeper.
	  placeholder: Rather than describing implementation details for this feature, try to describe what you are trying to achieve.
    validations:
      required: true
  - type: textarea
    attributes:
      label: Related issues
      description: Is there currently another issue associated with this?
	  placeholder: "Related: zach-overflow/beetkeeper/issues/<Issue number here>"
