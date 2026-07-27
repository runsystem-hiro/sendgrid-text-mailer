# Security Policy

## Supported Versions

Security fixes are provided for the latest version on the `main` branch.

## Reporting a Vulnerability

Do not report security vulnerabilities in public GitHub issues.

Please use GitHub's private vulnerability reporting feature if it is enabled
for this repository.

When reporting a vulnerability, include:

- A description of the issue
- Steps to reproduce it
- The affected version or commit
- The potential impact
- Any suggested mitigation

## Sensitive Information

Never commit the following information:

- SendGrid API keys
- `.env` files
- Real recipient lists
- Delivery history databases
- Production campaign files
- Internal email addresses or customer information

If a credential is accidentally committed, revoke and replace it immediately.
Removing it from the latest commit is not sufficient because it may remain in
Git history.
