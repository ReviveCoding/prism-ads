from __future__ import annotations

import pyro
import torch

from prism_ads.models.prism_hb import prism_hb_model, prism_hb_rate_model


def inputs() -> tuple[torch.Tensor, ...]:
    return (
        torch.tensor([20.0, 15.0]),
        torch.tensor([22.0, 18.0]),
        torch.tensor([2.1, 1.2]),
        torch.tensor([3.0, 2.4]),
        torch.tensor([0, 1]),
        torch.tensor([0, 0]),
        torch.tensor(1.5),
    )


def test_exact_and_rate_models_trace_all_hierarchy_branches() -> None:
    n0, n1, y0, y1, campaign, segment, sigma = inputs()
    exact = pyro.poutine.trace(prism_hb_model).get_trace(
        torch.full_like(n0, 20.0),
        torch.full_like(n1, 20.0),
        y0,
        y1,
        campaign,
        segment,
        2,
        1,
        sigma,
    )
    assert {"private_y0", "private_y1"} <= set(exact.nodes)
    full = pyro.poutine.trace(prism_hb_rate_model).get_trace(
        n0, n1, y0, y1, campaign, segment, 2, 1, sigma
    )
    assert "effect" in full.nodes
    minimal = pyro.poutine.trace(prism_hb_rate_model).get_trace(
        n0,
        n1,
        y0,
        y1,
        campaign,
        segment,
        2,
        1,
        sigma,
        use_campaign_hierarchy=False,
        use_segment_hierarchy=False,
        include_privacy_variance=False,
        use_effect_hierarchy=False,
    )
    assert "campaign_alpha_scale" not in minimal.nodes


def test_rate_model_response_only_hierarchies() -> None:
    n0, n1, y0, y1, campaign, segment, sigma = inputs()
    trace = pyro.poutine.trace(prism_hb_rate_model).get_trace(
        n0,
        n1,
        y0,
        y1,
        campaign,
        segment,
        2,
        1,
        sigma,
        use_effect_hierarchy=False,
    )
    assert "campaign_alpha_raw" in trace.nodes
    assert "campaign_tau_raw" not in trace.nodes
