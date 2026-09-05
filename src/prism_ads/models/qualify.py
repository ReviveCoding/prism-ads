# mypy: disable-error-code="no-untyped-call"
"""GPU-backed Tier-A MCMC smoke recovery and diagnostic evidence."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyro
import torch
from pyro.infer import MCMC, NUTS
from pyro.ops.stats import effective_sample_size, gelman_rubin

from prism_ads.experiments.t3_generator import publish_json, sha256_file, utc_now
from prism_ads.models.prism_hb import prism_hb_model


def _diagnostic_summary(samples: dict[str, torch.Tensor], divergences: int) -> dict[str, Any]:
    r_hats = [
        value
        for sample in samples.values()
        for value in gelman_rubin(sample).reshape(-1).tolist()
    ]
    effective = [
        value
        for sample in samples.values()
        for value in effective_sample_size(sample).reshape(-1).tolist()
    ]
    return {
        "max_r_hat": max(r_hats) if r_hats else None,
        "min_effective_sample_size": min(effective) if effective else None,
        "divergences": divergences,
    }


def run(root: Path) -> dict[str, Any]:
    root = root.resolve()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the P08 GPU qualification")
    device = torch.device("cuda")
    pyro.set_rng_seed(2026090408)
    torch.set_default_dtype(torch.float64)
    campaign_index = torch.tensor([0, 0, 0, 1, 1, 1], device=device)
    segment_index = torch.tensor([0, 1, 2, 0, 1, 2], device=device)
    n0 = torch.full((6,), 25.0, device=device)
    n1 = torch.full((6,), 25.0, device=device)
    baseline_logit = torch.tensor([-2.8, -2.6, -2.5, -3.0, -2.7, -2.4], device=device)
    true_tau = torch.tensor([0.15, 0.25, 0.35, 0.10, 0.20, 0.30], device=device)
    latent_y0 = torch.distributions.Binomial(n0, logits=baseline_logit).sample()
    latent_y1 = torch.distributions.Binomial(n1, logits=baseline_logit + true_tau).sample()
    privacy_sigma = torch.tensor(1.25, device=device)
    noisy_y0 = latent_y0 + torch.randn_like(latent_y0) * privacy_sigma
    noisy_y1 = latent_y1 + torch.randn_like(latent_y1) * privacy_sigma
    torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    chain_results: list[dict[str, torch.Tensor]] = []
    divergences = 0
    for chain in range(2):
        pyro.set_rng_seed(2026090410 + chain)
        kernel = NUTS(prism_hb_model, target_accept_prob=0.85, max_tree_depth=6)
        inference = MCMC(
            kernel,
            num_samples=80,
            warmup_steps=80,
            num_chains=1,
            disable_progbar=True,
        )
        inference.run(
            n0,
            n1,
            noisy_y0,
            noisy_y1,
            campaign_index,
            segment_index,
            2,
            3,
            privacy_sigma,
        )
        chain_results.append(inference.get_samples(group_by_chain=False))
        chain_diagnostics = inference.diagnostics().get("divergences", {})
        divergences += sum(len(items) for items in chain_diagnostics.values())
    torch.cuda.synchronize()
    runtime = time.perf_counter() - started
    samples = {
        name: torch.stack([chain[name] for chain in chain_results])
        for name in chain_results[0]
    }
    diagnostics = _diagnostic_summary(samples, divergences)
    posterior_mu_tau = float(samples["mu_tau"].mean().detach().cpu())
    mu_tau_values = samples["mu_tau"].reshape(-1)
    mu_tau_interval = [
        float(torch.quantile(mu_tau_values, 0.025).detach().cpu()),
        float(torch.quantile(mu_tau_values, 0.975).detach().cpu()),
    ]
    true_tau_mean = float(true_tau.mean().cpu())
    smoke_recovery = mu_tau_interval[0] <= true_tau_mean <= mu_tau_interval[1]
    output = root / "artifacts" / "qualification" / "P08"
    output.mkdir(parents=True, exist_ok=True)
    sample_path = output / "mcmc_samples.pt"
    temporary = sample_path.with_suffix(".pt.tmp")
    torch.save({key: value.detach().cpu() for key, value in samples.items()}, temporary)
    os.replace(temporary, sample_path)
    sample_path.chmod(0o444)
    health = (
        diagnostics["max_r_hat"] is not None
        and diagnostics["max_r_hat"] < 1.25
        and diagnostics["min_effective_sample_size"] is not None
        and diagnostics["min_effective_sample_size"] >= 10
        and diagnostics["divergences"] == 0
        and smoke_recovery
    )
    result = {
        "phase": "P08",
        "validated_at": utc_now(),
        "status": "PASS" if health else "FAIL",
        "model_id": "PRISM-HB-pyro-exact-latent-v1",
        "backend": "Pyro 1.9.1 / PyTorch 2.14.0+cu130",
        "device": torch.cuda.get_device_name(0),
        "cuda": torch.version.cuda,
        "chains": 2,
        "warmup": 80,
        "draws_per_chain": 80,
        "target_accept_probability": 0.85,
        "diagnostics": diagnostics,
        "posterior_mu_tau": posterior_mu_tau,
        "posterior_mu_tau_95_interval": mu_tau_interval,
        "true_tau_mean_smoke_only": true_tau_mean,
        "smoke_recovery_interval_contains_truth": smoke_recovery,
        "runtime_seconds": runtime,
        "peak_vram_bytes": torch.cuda.max_memory_allocated(),
        "likelihood": "exact Binomial latent count marginalized under Gaussian privacy noise",
        "candidate_inputs": ["n0", "n1", "noisy_y0", "noisy_y1", "privacy_sigma"],
        "samples": {
            "path": str(sample_path.relative_to(root)).replace("\\", "/"),
            "bytes": sample_path.stat().st_size,
            "sha256": sha256_file(sample_path),
        },
    }
    publish_json(output / "inference_diagnostics.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = run(args.root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
