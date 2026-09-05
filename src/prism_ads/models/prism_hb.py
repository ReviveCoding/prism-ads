# mypy: disable-error-code="no-untyped-call"
"""Privacy-Aware Hierarchical Bayesian Incrementality Estimator."""

from __future__ import annotations

import pyro
import pyro.distributions as dist
import torch
from torch import Tensor


def private_count_log_prob(
    noisy_count: Tensor,
    total_count: Tensor,
    probability: Tensor,
    privacy_sigma: Tensor,
) -> Tensor:
    """Exactly marginalize latent Binomial counts under a Gaussian DP observation."""
    maximum = int(total_count.max().detach().cpu().item())
    latent = torch.arange(maximum + 1, device=noisy_count.device, dtype=noisy_count.dtype)
    latent = latent.unsqueeze(0)
    totals = total_count.unsqueeze(1)
    probabilities = probability.unsqueeze(1)
    valid = latent <= totals
    binomial = dist.Binomial(total_count=totals, probs=probabilities).log_prob(latent)
    privacy = dist.Normal(latent, privacy_sigma).log_prob(noisy_count.unsqueeze(1))
    joint = torch.where(valid, binomial + privacy, torch.full_like(binomial, -torch.inf))
    return torch.logsumexp(joint, dim=1)


def prism_hb_model(
    n0: Tensor,
    n1: Tensor,
    noisy_y0: Tensor,
    noisy_y1: Tensor,
    campaign_index: Tensor,
    segment_index: Tensor,
    campaign_count: int,
    segment_count: int,
    privacy_sigma: Tensor,
) -> None:
    """Non-centered response/effect hierarchy with an exact latent privacy likelihood."""
    device = n0.device
    zero = torch.tensor(0.0, device=device)
    one = torch.tensor(1.0, device=device)
    alpha = pyro.sample("alpha", dist.Normal(torch.tensor(-3.0, device=device), one))
    campaign_alpha_scale = pyro.sample("campaign_alpha_scale", dist.HalfNormal(one * 0.5))
    segment_alpha_scale = pyro.sample("segment_alpha_scale", dist.HalfNormal(one * 0.5))
    campaign_alpha_raw = pyro.sample(
        "campaign_alpha_raw",
        dist.Normal(zero, one).expand([campaign_count]).to_event(1),
    )
    segment_alpha_raw = pyro.sample(
        "segment_alpha_raw",
        dist.Normal(zero, one).expand([segment_count]).to_event(1),
    )
    mu_tau = pyro.sample("mu_tau", dist.Normal(zero, one * 0.5))
    campaign_tau_scale = pyro.sample("campaign_tau_scale", dist.HalfNormal(one * 0.35))
    segment_tau_scale = pyro.sample("segment_tau_scale", dist.HalfNormal(one * 0.35))
    campaign_tau_raw = pyro.sample(
        "campaign_tau_raw",
        dist.Normal(zero, one).expand([campaign_count]).to_event(1),
    )
    segment_tau_raw = pyro.sample(
        "segment_tau_raw",
        dist.Normal(zero, one).expand([segment_count]).to_event(1),
    )
    logit0 = (
        alpha
        + campaign_alpha_scale * campaign_alpha_raw[campaign_index]
        + segment_alpha_scale * segment_alpha_raw[segment_index]
    )
    tau = (
        mu_tau
        + campaign_tau_scale * campaign_tau_raw[campaign_index]
        + segment_tau_scale * segment_tau_raw[segment_index]
    )
    p0 = torch.sigmoid(logit0)
    p1 = torch.sigmoid(logit0 + tau)
    pyro.factor("private_y0", private_count_log_prob(noisy_y0, n0, p0, privacy_sigma).sum())
    pyro.factor("private_y1", private_count_log_prob(noisy_y1, n1, p1, privacy_sigma).sum())


def prism_hb_rate_model(
    noisy_n0: Tensor,
    noisy_n1: Tensor,
    noisy_y0: Tensor,
    noisy_y1: Tensor,
    campaign_index: Tensor,
    segment_index: Tensor,
    campaign_count: int,
    segment_count: int,
    privacy_sigma: Tensor,
    use_campaign_hierarchy: bool = True,
    use_segment_hierarchy: bool = True,
    include_privacy_variance: bool = True,
    use_effect_hierarchy: bool = True,
    effect_scale_prior: float = 0.35,
) -> None:
    """Scalable rate likelihood propagating numerator and denominator DP noise."""
    device = noisy_n0.device
    zero = torch.tensor(0.0, device=device)
    one = torch.tensor(1.0, device=device)
    alpha = pyro.sample("alpha", dist.Normal(torch.tensor(-3.0, device=device), one))
    mu_tau = pyro.sample("mu_tau", dist.Normal(zero, one * 0.5))
    logit0 = alpha.expand_as(noisy_n0)
    tau = mu_tau.expand_as(noisy_n0)
    if use_campaign_hierarchy:
        alpha_scale = pyro.sample("campaign_alpha_scale", dist.HalfNormal(one * 0.5))
        alpha_raw = pyro.sample(
            "campaign_alpha_raw",
            dist.Normal(zero, one).expand([campaign_count]).to_event(1),
        )
        logit0 = logit0 + alpha_scale * alpha_raw[campaign_index]
        if use_effect_hierarchy:
            tau_scale = pyro.sample("campaign_tau_scale", dist.HalfNormal(one * effect_scale_prior))
            tau_raw = pyro.sample(
                "campaign_tau_raw",
                dist.Normal(zero, one).expand([campaign_count]).to_event(1),
            )
            tau = tau + tau_scale * tau_raw[campaign_index]
    if use_segment_hierarchy:
        alpha_scale = pyro.sample("segment_alpha_scale", dist.HalfNormal(one * 0.5))
        alpha_raw = pyro.sample(
            "segment_alpha_raw",
            dist.Normal(zero, one).expand([segment_count]).to_event(1),
        )
        logit0 = logit0 + alpha_scale * alpha_raw[segment_index]
        if use_effect_hierarchy:
            tau_scale = pyro.sample("segment_tau_scale", dist.HalfNormal(one * effect_scale_prior))
            tau_raw = pyro.sample(
                "segment_tau_raw",
                dist.Normal(zero, one).expand([segment_count]).to_event(1),
            )
            tau = tau + tau_scale * tau_raw[segment_index]
    p0 = torch.sigmoid(logit0)
    p1 = torch.sigmoid(logit0 + tau)
    effective_n0 = noisy_n0.clamp_min(1.0)
    effective_n1 = noisy_n1.clamp_min(1.0)
    rate0 = noisy_y0 / effective_n0
    rate1 = noisy_y1 / effective_n1
    privacy = privacy_sigma.square() if include_privacy_variance else zero
    variance0 = p0 * (1 - p0) / effective_n0 + privacy * (1 + p0.square()) / effective_n0.square()
    variance1 = p1 * (1 - p1) / effective_n1 + privacy * (1 + p1.square()) / effective_n1.square()
    pyro.sample("private_rate0", dist.Normal(p0, variance0.sqrt()).to_event(1), obs=rate0)
    pyro.sample("private_rate1", dist.Normal(p1, variance1.sqrt()).to_event(1), obs=rate1)
    pyro.deterministic("effect", p1 - p0)
