//! Process-wide, immutable selected model destination contract.
//! Tool, MCP and SSO networking remain outside this model transport policy.
use crate::NetworkPolicyDenied;
use reqwest::Url;
use std::sync::OnceLock;

static PRIVATE_POLICY: OnceLock<PrivatePolicy> = OnceLock::new();

#[derive(Debug)]
struct PrivatePolicy {
    endpoints: Vec<Url>,
}

impl PrivatePolicy {
    fn parse(endpoints: &[String]) -> Result<Self, &'static str> {
        let mut parsed = Vec::new();
        for endpoint in endpoints {
            let url = Url::parse(endpoint).map_err(|_| "invalid private model endpoint")?;
            let local = url
                .host_str()
                .is_some_and(|host| host == "127.0.0.1" || host == "[::1]");
            let host = url.host_str().unwrap_or_default();
            if !(url.scheme() == "https" || (url.scheme() == "http" && local))
                || host.is_empty()
                || !url.username().is_empty()
                || url.password().is_some()
                || url.query().is_some()
                || url.fragment().is_some()
                || ["openai.com", "chatgpt.com", "anthropic.com"]
                    .iter()
                    .any(|domain| host == *domain || host.ends_with(&format!(".{domain}")))
                || (url.scheme() == "http" && url.port().is_none())
            {
                return Err(
                    "private model endpoint must be a credential-free company HTTPS base or explicit loopback HTTP base",
                );
            }
            parsed.push(url);
        }
        Ok(Self { endpoints: parsed })
    }
    fn allows(&self, url: &Url) -> bool {
        if !url.username().is_empty()
            || url.password().is_some()
            || url.query().is_some()
            || url.fragment().is_some()
        {
            return false;
        }
        self.endpoints.iter().any(|base| {
            base.scheme() == url.scheme()
                && base.host_str() == url.host_str()
                && base.port_or_known_default() == url.port_or_known_default()
                && ["responses", "chat/completions", "messages"]
                    .iter()
                    .any(|route| {
                        url.path() == format!("{}/{route}", base.path().trim_end_matches('/'))
                    })
        })
    }
}

/// Install once, before any transport or worker starts. An empty list denies all.
/// Errors deliberately never include URLs, credentials or request payloads.
pub fn initialize_private_runtime(endpoints: &[String]) -> Result<(), &'static str> {
    let policy = PrivatePolicy::parse(endpoints)?;
    PRIVATE_POLICY
        .set(policy)
        .map_err(|_| "private runtime policy was already initialized")
}
pub fn private_runtime_enabled() -> bool {
    PRIVATE_POLICY.get().is_some()
}
pub fn check_private_model_destination(url: &Url) -> Result<(), NetworkPolicyDenied> {
    if PRIVATE_POLICY
        .get()
        .is_some_and(|policy| !policy.allows(url))
    {
        return Err(NetworkPolicyDenied::Destination);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn private_endpoint_policy() {
        let policy = PrivatePolicy::parse(&[
            "https://models.company.test/v1".to_string(),
            "http://127.0.0.1:8123/v1".to_string(),
        ])
        .unwrap();
        for url in [
            "https://models.company.test/v1/responses",
            "http://127.0.0.1:8123/v1/responses",
        ] {
            assert!(policy.allows(&reqwest::Url::parse(url).unwrap()), "{url}");
        }
        for url in [
            "https://api.openai.com/v1/responses",
            "https://models.company.test/telemetry",
            "https://models.company.test:8443/v1/responses",
            "http://127.0.0.1:8124/v1/responses",
            "https://models.company.test/v1/responses/extra",
            "https://models.company.test/v1/responses?upload=1",
        ] {
            assert!(!policy.allows(&reqwest::Url::parse(url).unwrap()), "{url}");
        }
        assert!(
            !PrivatePolicy::parse(&[])
                .unwrap()
                .allows(&reqwest::Url::parse("https://models.company.test/v1/responses").unwrap())
        );
        for endpoint in [
            "http://models.company.test/v1",
            "https://api.openai.com/v1",
            "https://user:password@models.company.test/v1",
            "https://models.company.test/v1?key=secret",
            "http://localhost:8123/v1",
        ] {
            assert!(
                PrivatePolicy::parse(&[endpoint.to_string()]).is_err(),
                "{endpoint}"
            );
        }
    }
}
