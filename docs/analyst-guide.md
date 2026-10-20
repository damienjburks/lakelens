# LakeLens — Analyst Guide

This guide is for security analysts who use the LakeLens to explore and investigate Security Hub findings. No programming or SQL knowledge is required.

## How the Agent Works

LakeLens lets you ask questions about your Security Hub findings in plain English. Here's what happens behind the scenes when you ask a question:

1. **You ask a question** — Type your question naturally, like you'd ask a colleague
2. **LakeLens looks up context** — It can retrieve approved table metadata through the Glue schema lookup tool. No knowledge base is attached in the current deployment
3. **It generates a safe query** — The agent writes a read-only SQL query against your Security Lake data
4. **The query is validated** — An automated safety check ensures the query only reads approved tables, stays within time limits, and cannot modify anything
5. **Results come back** — The validated query runs, and results are returned to the agent
6. **You get a summary** — The agent explains the results in plain language, maps findings to MITRE ATT&CK techniques when relevant, and recommends detective, corrective, or preventative controls

The agent is strictly read-only. It can look at your findings data and explain what it sees, but it cannot change, fix, or remediate anything. Recommendations are always suggestions for your team to evaluate and implement.

## Effective Prompt Patterns

Different question styles produce different types of results. Here are four patterns that work well:

### Broad Questions (Summaries and Aggregations)

Use these when you want the big picture. The agent will aggregate and summarize.

- "What are the top finding types this week?"
- "Summarize Security Hub findings by severity over the last 7 days"
- "Which AWS accounts have the most critical findings?"
- "What's the overall security posture trend over the last 30 days?"

### Scoped Questions (Filtered and Detailed)

Use these when you want to drill into a specific area. Include account IDs, resource types, severity levels, or time ranges.

- "Show me high-severity findings for account 123456789012 from the last 24 hours"
- "What failed security controls are associated with S3 buckets?"
- "List findings with severity CRITICAL that are still ACTIVE"
- "Which EC2 instances have security group findings in the last 48 hours?"

### Follow-Up Questions (Iterative Investigation)

Use these to dig deeper after an initial response. The agent maintains context from the conversation.

- "Drill into the top finding type from that list"
- "Which of those could be auto-remediated?"
- "Map those findings to MITRE ATT&CK"
- "Show me the affected resources for the top 3 finding types"

### Control Recommendation Questions

Use these to get actionable guidance. The agent recommends 1–3 controls for each finding, each categorized as detective, corrective, or preventative, and names the specific AWS service or feature.

- "What corrective controls should I apply for these findings?"
- "Recommend detective controls for the S3 misconfigurations"
- "Which AWS services would help prevent these finding types?"
- "What controls map to the MITRE techniques you identified?"

## What the Agent Can Do

- **Query Security Hub findings** stored in Security Lake (OCSF format)
- **Aggregate, filter, and summarize** finding data by severity, account, resource type, time range, and more
- **Explain finding types** — what they mean, why they matter, and what resources are affected
- **Map findings to MITRE ATT&CK** techniques and tactics
- **Recommend controls** — detective, corrective, and preventative — with specific AWS services named
- **Justify recommendations** by referencing the finding type, affected resource, and relevant AWS security best practices
- **Explain query results** in plain language so you understand what the data shows

## What the Agent Cannot Do

- **Remediate findings** — it cannot modify, fix, or change any AWS resource
- **Access unapproved tables** — it can only query the Security Lake tables your team has approved
- **Query old data** — it cannot look back further than the configured lookback window (default: 90 days)
- **Return unlimited results** — queries are capped at 1,000 rows by default to keep responses manageable
- **Execute destructive operations** — no deletes, updates, or modifications of any kind
- **Access non-Security-Lake data** — it only sees Security Hub findings synced to Security Lake
- **Make enforcement decisions** — all control recommendations require human review before implementation
- **See real-time state** — it queries point-in-time snapshots synced to Security Lake, not live Security Hub

## Worked Conversation Examples

### Example 1: Severity Overview

> **Analyst:** "Show me a breakdown of Security Hub findings by severity from the last week."
>
> **Agent:** "Here's the severity breakdown from the last 7 days:
>
> - CRITICAL: 3 findings
> - HIGH: 12 findings
> - MEDIUM: 47 findings
> - LOW: 89 findings
>
> The 3 critical findings involve exposed S3 buckets and disabled CloudTrail logging. I recommend prioritizing these immediately.
>
> **Detective controls:** Enable AWS Config rules for `s3-bucket-public-read-prohibited` and `cloudtrail-enabled`.
>
> **Corrective controls:** Use AWS Systems Manager Automation to remediate S3 public access and re-enable CloudTrail."

---

### Example 2: Account-Scoped Investigation

> **Analyst:** "What are the active findings for account 111222333444 over the last 30 days?"
>
> **Agent:** "Account 111222333444 has 23 active findings over the last 30 days. Top categories:
>
> - IAM Access Analyzer findings (8)
> - S3 bucket policy issues (7)
> - Security group misconfigurations (5)
> - Encryption disabled (3)
>
> The IAM findings suggest overly permissive roles. This maps to MITRE ATT&CK T1078 (Valid Accounts).
>
> **Recommended:** Review IAM Access Analyzer recommendations and tighten least-privilege policies using IAM Access Analyzer's policy generation feature."

---

### Example 3: MITRE ATT&CK Mapping

> **Analyst:** "Map the critical findings to MITRE ATT&CK"
>
> **Agent:** "Critical findings mapped to MITRE ATT&CK:
>
> | Finding             | Technique                                          | Tactic          |
> | ------------------- | -------------------------------------------------- | --------------- |
> | Public S3 bucket    | T1530 — Data from Cloud Storage Object             | Collection      |
> | Disabled CloudTrail | T1562.008 — Impair Defenses: Disable Cloud Logs    | Defense Evasion |
> | Root account usage  | T1078.004 — Valid Accounts: Cloud Accounts         | Initial Access  |
>
> These primarily align with Initial Access and Defense Evasion tactics, suggesting an attacker could be establishing persistence or covering tracks."

---

### Example 4: Control Recommendations with Follow-Up

> **Analyst:** "What corrective controls should I apply for the S3 findings?"
>
> **Agent:** "For the S3 bucket policy findings, I recommend:
>
> 1. **Corrective** — Enable S3 Block Public Access at the account level using AWS Organizations SCPs to prevent future public buckets
> 2. **Detective** — Deploy the AWS Config managed rule `s3-bucket-public-read-prohibited` to detect new violations within minutes
> 3. **Preventative** — Apply an S3 bucket policy that denies `s3:PutBucketPolicy` actions that would grant public access
>
> These controls address CIS AWS Foundations Benchmark control 2.1.1 (Ensure S3 buckets do not allow public access)."
>
> **Analyst:** "Which of those is fastest to implement?"
>
> **Agent:** "Enabling S3 Block Public Access at the account level is the fastest — it's a single API call per account and immediately blocks all public access for existing and new buckets. You can do this through the S3 console or via the `aws s3control put-public-access-block` CLI command. Note: verify no buckets intentionally serve public content before enabling."

---

### Example 5: Time-Bounded Trend Analysis

> **Analyst:** "Show me how critical findings have trended over the last 30 days, broken down weekly."
>
> **Agent:** "Critical findings trend over the last 30 days:
>
> - Week 1 (30–24 days ago): 2 critical findings
> - Week 2 (23–17 days ago): 4 critical findings
> - Week 3 (16–10 days ago): 7 critical findings
> - Week 4 (9–3 days ago): 3 critical findings
>
> There was a spike in Week 3, driven primarily by new IAM findings after a role policy change. The drop in Week 4 suggests your team's remediation efforts are working.
>
> **Detective control:** Set up an Amazon EventBridge rule to alert on new CRITICAL findings in near real-time so spikes are caught faster."

## Tips for Best Results

- **Be specific about time ranges** — "last 24 hours" or "last 7 days" gives better results than "recently" or "lately"
- **Include account IDs** when investigating a specific account — the agent can filter precisely
- **Start broad, then drill down** — ask for a summary first ("show me a summary"), then follow up on what stands out ("detail the top 5 finding types")
- **Ask for control categories** — specify "detective", "corrective", or "preventative" if you want a specific type of recommendation
- **Request MITRE mappings** after reviewing findings to understand attacker techniques and prioritize response
- **If results seem incomplete**, ask the agent to explain its query — you can verify whether the right filters were applied
- **Use follow-ups freely** — the agent remembers the conversation context, so you can iteratively narrow your investigation

## Limitations

- **Point-in-time data** — The agent queries data that has been synced to Security Lake. There may be a short delay between a finding appearing in Security Hub and being available for query.
- **MITRE mappings are best-effort** — Mappings are based on finding type patterns and are informational, not authoritative. Validate mappings against the official MITRE ATT&CK framework for formal reporting.
- **Control recommendations require human review** — All suggestions are starting points. Your team should evaluate feasibility, blast radius, and organizational context before implementing any control.
- **No real-time Security Hub access** — The agent sees only what has been synced to Security Lake, not the live Security Hub state.
- **Data retention limits apply** — The agent cannot query findings older than the configured lookback window (default: 90 days). For historical analysis beyond this window, contact your platform team.
- **Row limits apply** — Individual queries return a maximum of 1,000 rows (configurable by your platform team). If you need larger data sets, ask narrower questions or request your team adjust the limit.
