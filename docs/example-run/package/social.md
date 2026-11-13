# From Finding to Reviewable Repair

WebOps Factory’s repository describes a visible path from a supported static-site finding to a checked repair candidate. It works on a copy, retains the exact diff and supporting evidence, and sends the patch to an independent model reviewer. The original site is not edited. [copied-site-repair-and-review-workflow, reviewable-run-outputs]

The workflow stops at human review: it neither approves nor deploys the candidate. See the repository README for complete prerequisites, setup and review guidance: https://github.com/kujolang/webops-factory [verification-commands-and-human-review, reader-action-open-repository-readme]


---

# Focused Repairs, Visible Boundaries

The WebOps Factory repository says the current release supports four repair categories: missing or empty titles, missing or empty search descriptions, images without alt attributes and broken internal file links. It also says failed checks or requested revisions leave the run blocked with its evidence rather than producing an approval package. [supported-repair-types, controller-input-and-failure-boundaries]

The repository describes a bounded scope: static exports only, not framework projects or server applications. Its checks do not establish perfect SEO, accessibility conformance or security certification. Human review and deployment remain separate. Open the repository README for complete, current prerequisites, setup instructions and review guidance: https://github.com/kujolang/webops-factory [static-export-intake-boundaries, coverage-and-exclusions, verification-commands-and-human-review]


---

# Evidence Reviewers Can Inspect

WebOps Factory’s repository says each run retains the imported bytes, repaired candidate, before-and-after findings, specialist and independent-review responses, exact repair diff, SiteProbe and Lens artifacts, and a package binding the candidate and evidence to file hashes. [reviewable-run-outputs]

Those records support inspection; they do not prove that a repair is correct or ready for release. Browser checks cover the homepage at desktop and mobile sizes, while the static audit examines imported HTML pages. Review the README for full setup and review guidance: https://github.com/kujolang/webops-factory [reviewable-run-outputs, coverage-and-exclusions, reader-action-open-repository-readme]
