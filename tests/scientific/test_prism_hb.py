from __future__ import annotations

import torch

from prism_ads.models.prism_hb import private_count_log_prob


def test_private_count_likelihood_is_finite_and_differentiable() -> None:
    probability = torch.tensor([0.2, 0.4], dtype=torch.float64, requires_grad=True)
    value = private_count_log_prob(
        noisy_count=torch.tensor([2.2, 3.7], dtype=torch.float64),
        total_count=torch.tensor([10.0, 10.0], dtype=torch.float64),
        probability=probability,
        privacy_sigma=torch.tensor(1.5, dtype=torch.float64),
    ).sum()
    assert torch.isfinite(value)
    value.backward()
    assert probability.grad is not None
    assert torch.all(torch.isfinite(probability.grad))


def test_private_likelihood_accepts_noninteger_noisy_counts() -> None:
    result = private_count_log_prob(
        torch.tensor([-0.4]), torch.tensor([5.0]), torch.tensor([0.1]), torch.tensor(2.0)
    )
    assert result.shape == (1,)
    assert torch.isfinite(result).all()
