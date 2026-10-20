# LakeLens — Investigation Test Prompts

## Quick Smoke Tests (fast, small data)

1. Show me 3 findings from the last day.
2. How many findings by severity level do I have from the last day?
3. What finding types exist in the last 24 hours?

## Severity & Triage

4. What are the top 5 finding types by count from the last 3 days?
5. Show me all critical findings from the last day. What should I prioritize?
6. Are there any high or critical findings that are still in "New" status?

## Account-Level Investigation

7. Which accounts have the most findings in the last 3 days?
8. Show me findings for account 748355717020 from the last day.
9. Compare finding counts across all my accounts from the last 3 days.

## Resource-Level Investigation

10. Which resource types have the most findings in the last 3 days?
11. Are there any S3 buckets with active findings from the last day?
12. Show me IAM-related findings from the last 3 days and explain the risk.

## Compliance & Controls

13. Which compliance controls are failing the most in the last 3 days?
14. Show me CIS benchmark failures from the last day.
15. What CloudTrail-related findings do I have? Are my audit logs at risk?

## MITRE ATT&CK Mapping

16. Map my top findings from the last day to MITRE ATT&CK techniques.
17. Do I have any findings that indicate credential compromise (T1078)?
18. Which findings suggest defense evasion tactics?

## Control Recommendations

19. What corrective controls should I apply for my S3 findings?
20. Recommend detective controls for the IAM issues you found.
21. Give me preventative controls for my top 3 finding types.

## Follow-Up Conversations (use in sequence)

22. What are my top issues from today?
23. Drill into the most common finding type.
24. What MITRE techniques does that map to?
25. Recommend controls to fix it.

## Edge Cases & Stress Tests

26. Show me findings with severity "Unknown" from the last 3 days.
27. Are there any findings that have been active for more than 7 days?
28. What's the oldest unresolved finding in the last 30 days?
