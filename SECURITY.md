# Security Policy

Do not report vulnerabilities in public issues.

Until a private reporting address is established, use GitHub's private vulnerability reporting feature for the repository.

Sensitive values such as passwords, tokens, and API keys must never be committed. Future releases will encrypt stored integration secrets and keep integration requests on the backend.

Live status checks are backend-originated requests to service URLs configured by an authenticated dashboard administrator. Public HTTPS targets require valid certificates. Private/local targets may use self-signed certificates for homelab compatibility.

## Theme packages

Imported themes are treated as untrusted data. The supported theme package format accepts only validated metadata and six-digit hexadecimal design tokens. Theme packages cannot contain executable JavaScript, arbitrary CSS, remote resource URLs, Docker permissions, filesystem access, or access to stored service credentials.
