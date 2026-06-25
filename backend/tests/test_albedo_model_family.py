"""Tests for Albedo model-family inference from Hippius repo paths."""

from app.chain_reader.albedo_model_family import (
    FAMILY_QWEN36_35B,
    FAMILY_QWEN3_4B,
    infer_albedo_model_family,
    repo_from_slot_detail,
)


def test_qwen3_4b_canonical():
    assert infer_albedo_model_family("miner/albedo-qwen3-4b-run1") == FAMILY_QWEN3_4B
    assert infer_albedo_model_family("teutonic/albedo-qwen3-4b-genesis") == FAMILY_QWEN3_4B


def test_qwen36_35b_canonical():
    assert infer_albedo_model_family("miner/albedo-qwen3.6-35b-v1") == FAMILY_QWEN36_35B
    assert infer_albedo_model_family("teutonic/albedo-qwen3.6-35b-genesis") == FAMILY_QWEN36_35B


def test_loose_hints():
    assert infer_albedo_model_family("x/custom-qwen3.6-35b-trial") == FAMILY_QWEN36_35B
    assert infer_albedo_model_family("x/my-qwen3_4b-fork") == FAMILY_QWEN3_4B


def test_unknown_or_invalid():
    assert infer_albedo_model_family(None) is None
    assert infer_albedo_model_family("") is None
    assert infer_albedo_model_family("not-a-repo") is None
    assert infer_albedo_model_family("org/random-model") is None


def test_repo_from_slot_detail():
    assert repo_from_slot_detail("a/albedo-qwen3.6-35b-v2", "v7") == "a/albedo-qwen3.6-35b-v2"
    assert repo_from_slot_detail("a/albedo-qwen3.6-35b-v2", "v6") == "a/albedo-qwen3.6-35b-v2"
    assert repo_from_slot_detail("round:12345", "timelock_encrypted") is None
